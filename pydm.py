#!/usr/bin/env python3
"""PyDM - gestionnaire de téléchargement multi-connexions (style IDM) pour Linux.

  Interface graphique :  python3 pydm.py
  Ligne de commande   :  python3 pydm.py URL [-o DOSSIER] [-n CONNEXIONS] [-q QUALITE]

Fonctions : téléchargement découpé en plusieurs connexions parallèles,
découpage dynamique (une connexion libre reprend la moitié du plus gros
segment restant), pause / reprise même après fermeture, relance automatique
en cas de coupure, surveillance du presse-papiers.
Vidéos des sites de streaming (YouTube, Vimeo, Twitch, Dailymotion, TikTok,
flux HLS/DASH…) via yt-dlp s'il est installé : pip install -U yt-dlp
(ffmpeg recommandé pour la meilleure qualité et le MP3).
Aucune autre dépendance hors bibliothèque standard (Tkinter pour l'interface).
"""
import argparse
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from email.message import Message

CHUNK = 64 * 1024
MIN_SPLIT = 2 * 1024 * 1024
MAX_RETRIES = 6
UA = "Mozilla/5.0 (X11; Linux x86_64) PyDM/1.0"
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "pydm")
SESSION_FILE = os.path.join(CONFIG_DIR, "session.json")
SOCKET_PATH = os.path.join(CONFIG_DIR, "pydm.sock")
QUALITIES = {
    "Meilleure": "bv*+ba/b",
    "1080p": "bv*[height<=1080]+ba/b[height<=1080]/b",
    "720p": "bv*[height<=720]+ba/b[height<=720]/b",
    "480p": "bv*[height<=480]+ba/b[height<=480]/b",
    "Audio MP3": "ba/b",
}
BROWSERS = ("Aucun", "firefox", "chrome", "chromium", "brave", "edge", "opera", "vivaldi")
VIDEO_HOSTS = re.compile(
    r"(^|\.)(youtube\.com|youtu\.be|vimeo\.com|dailymotion\.com|dai\.ly|twitch\.tv|tiktok\.com|"
    r"instagram\.com|facebook\.com|fb\.watch|x\.com|twitter\.com|reddit\.com|soundcloud\.com|"
    r"bilibili\.com|rumble\.com|odysee\.com|bandcamp\.com|arte\.tv|france\.tv|streamable\.com)$", re.I)


def human(n):
    if n is None:
        return "?"
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if n < 1024:
            return f"{int(n)} {unit}" if unit == "o" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} Po"


def human_time(s):
    if s is None or s < 0:
        return ""
    s = int(s)
    h, rest = divmod(s, 3600)
    m, s = divmod(rest, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


def probe(url, headers=None):
    """Retourne (taille, accepte_les_plages, nom_de_fichier)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {}), "Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        final = r.geturl()
        cd = r.headers.get("Content-Disposition", "")
        if r.status == 206:
            m = re.search(r"/(\d+)\s*$", r.headers.get("Content-Range", ""))
            size = int(m.group(1)) if m else None
            ranges = size is not None
        else:
            cl = r.headers.get("Content-Length")
            size = int(cl) if cl else None
            ranges = False
    name = None
    if cd:
        msg = Message()
        msg["content-disposition"] = cd
        name = msg.get_filename()
    if not name:
        name = os.path.basename(urllib.parse.unquote(urllib.parse.urlparse(final).path))
    name = (name or "telechargement").replace("/", "_").strip() or "telechargement"
    return size, ranges, name


def unique_path(folder, name):
    base, ext = os.path.splitext(name)
    candidate, i = name, 1
    while any(os.path.exists(os.path.join(folder, candidate + suffix))
              for suffix in ("", ".part", ".pydm")):
        candidate = f"{base} ({i}){ext}"
        i += 1
    return candidate


class _Task:
    """Démarrage / pause communs aux deux types de téléchargement."""
    stop_evt = None
    _thread = None

    @property
    def finished(self):
        return self.status == "Terminé"

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self):
        if self.running or self.finished:
            return
        self.stop_evt.clear()
        self.error = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self):
        self.stop_evt.set()

    def wait(self, timeout=None):
        if self._thread:
            self._thread.join(timeout)


class Download(_Task):
    def __init__(self, url, folder, parts=8, name=None, headers=None, name_hint=None):
        self.url = url
        self.folder = folder
        self.headers = dict(headers or {})      # Cookie / Referer transmis par le navigateur
        self.name_hint = os.path.basename(name_hint) if name_hint else None
        self.parts = max(1, int(parts))
        self.name = name
        self.size = None
        self.ranges = False
        self.segments = []          # [début, fin incluse, octets reçus]
        self.status = "En attente"
        self.error = None
        self.speed = 0.0
        self.lock = threading.Lock()
        self.stop_evt = threading.Event()
        self._thread = None
        if name:
            self._load_state()

    # --- chemins / état -------------------------------------------------
    @property
    def path(self):
        return os.path.join(self.folder, self.name)

    @property
    def part_path(self):
        return self.path + ".part"

    @property
    def state_path(self):
        return self.path + ".pydm"

    @property
    def done(self):
        return sum(s[2] for s in self.segments)

    def _load_state(self):
        try:
            with open(self.state_path) as f:
                st = json.load(f)
        except (OSError, ValueError):
            if os.path.exists(self.path) and not os.path.exists(self.part_path):
                self.status = "Terminé"
                self.size = os.path.getsize(self.path)
                self.segments = [[0, self.size - 1, self.size]]
            return False
        if st.get("url") != self.url or not os.path.exists(self.part_path):
            return False
        self.size, self.ranges, self.segments = st["size"], st["ranges"], st["segments"]
        self.status = "En pause"
        return True

    def _save_state(self):
        with self.lock:
            data = {"url": self.url, "size": self.size, "ranges": self.ranges,
                    "segments": [list(s) for s in self.segments]}
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, self.state_path)

    def _prepare(self, size, ranges, name):
        os.makedirs(self.folder, exist_ok=True)
        if self.segments and self.size == size and self.ranges == ranges and os.path.exists(self.part_path):
            if not ranges:      # pas de reprise possible sans plages : on recommence
                self.segments = [[0, size - 1 if size else -1, 0]]
                open(self.part_path, "wb").close()
            return
        if not self.name:
            self.name = name
            if self._load_state() and self.size == size:
                return
            self.name = unique_path(self.folder, name)
        self.size, self.ranges = size, ranges
        if size and ranges:
            n = max(1, min(self.parts, size // MIN_SPLIT or 1))
            step = size // n
            self.segments = [[i * step, size - 1 if i == n - 1 else (i + 1) * step - 1, 0]
                             for i in range(n)]
        else:
            self.segments = [[0, size - 1 if size else -1, 0]]
        with open(self.part_path, "wb") as f:
            if size and ranges:
                f.truncate(size)

    # --- travail --------------------------------------------------------
    @staticmethod
    def _remaining(seg):
        return seg[1] - (seg[0] + seg[2]) + 1

    def _worker(self, seg):
        tries = 0
        while not self.stop_evt.is_set():
            if seg[1] >= 0 and self._remaining(seg) <= 0:
                return
            if not self.ranges:
                seg[2] = 0
            headers = {"User-Agent": UA, **self.headers}
            if self.ranges:
                headers["Range"] = f"bytes={seg[0] + seg[2]}-{seg[1]}"
            try:
                req = urllib.request.Request(self.url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as r, open(self.part_path, "r+b") as f:
                    if self.ranges and r.status != 206:
                        raise IOError("le serveur a ignoré la demande de plage")
                    while not self.stop_evt.is_set():
                        buf = r.read(CHUNK)
                        if not buf:
                            break
                        with self.lock:      # réserve la zone (le segment peut être redécoupé)
                            if seg[1] >= 0:
                                buf = buf[:max(0, self._remaining(seg))]
                            pos = seg[0] + seg[2]
                            seg[2] += len(buf)
                        if buf:
                            f.seek(pos)
                            f.write(buf)
                        tries = 0
                        if seg[1] >= 0 and self._remaining(seg) <= 0:
                            return
                    if seg[1] < 0 and not self.stop_evt.is_set():   # taille inconnue : fin du flux
                        seg[1] = seg[2] - 1
                        self.size = seg[2]
                        return
                if seg[1] >= 0 and self._remaining(seg) > 0 and not self.stop_evt.is_set():
                    raise IOError("connexion fermée prématurément")
            except Exception as e:  # noqa: BLE001 - toute erreur réseau déclenche une relance
                tries += 1
                if tries > MAX_RETRIES:
                    self.error = str(e)
                    self.stop_evt.set()
                    return
                self.stop_evt.wait(min(2 ** tries, 30))

    def _run(self):
        try:
            self.status = "Connexion…"
            size, ranges, name = probe(self.url, self.headers)
            self._prepare(size, ranges, self.name_hint or name)
        except Exception as e:  # noqa: BLE001
            self.error = str(e)
            self.status = f"Erreur : {e}"
            return

        self.status = "Téléchargement"
        threads = []

        def launch(seg):
            t = threading.Thread(target=self._worker, args=(seg,), daemon=True)
            t.start()
            threads.append(t)

        for seg in list(self.segments):
            if seg[1] < 0 or self._remaining(seg) > 0:
                launch(seg)

        last_done, last_t, last_save = self.done, time.time(), time.time()
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)
            now = time.time()
            inst = (self.done - last_done) / max(now - last_t, 1e-6)
            self.speed = inst if self.speed == 0 else 0.7 * self.speed + 0.3 * inst
            last_done, last_t = self.done, now

            # découpage dynamique : une connexion libre prend la moitié du plus gros reste
            alive = sum(t.is_alive() for t in threads)
            if self.ranges and not self.stop_evt.is_set() and alive < self.parts:
                new = None
                with self.lock:
                    big = max(self.segments, key=self._remaining)
                    rem = self._remaining(big)
                    if rem > MIN_SPLIT:
                        mid = big[0] + big[2] + rem // 2
                        new = [mid, big[1], 0]
                        big[1] = mid - 1
                        self.segments.append(new)
                if new:
                    launch(new)

            if now - last_save > 2:
                self._save_state()
                last_save = now

        self.speed = 0.0
        if self.stop_evt.is_set():
            self._save_state()
            self.status = f"Erreur : {self.error}" if self.error else "En pause"
            return
        os.replace(self.part_path, self.path)
        try:
            os.remove(self.state_path)
        except OSError:
            pass
        self.size = self.done
        self.status = "Terminé"


class _Paused(Exception):
    pass


class VideoDownload(_Task):
    """Vidéo d'un site de streaming, téléchargée par yt-dlp (fragments en parallèle)."""

    def __init__(self, url, folder, parts=8, name=None, quality="Meilleure", browser="Aucun",
                 headers=None):
        self.url = url
        self.headers = dict(headers or {})
        self.folder = folder
        self.parts = max(1, int(parts))
        self.name = name
        self.quality = quality
        self.browser = browser
        self.size = None
        self.done = 0
        self.speed = 0.0
        self.error = None
        self.stop_evt = threading.Event()
        self.status = "Terminé" if name and os.path.exists(self.path) else (
            "En pause" if name else "En attente")

    @property
    def path(self):
        return os.path.join(self.folder, self.name or "")

    def _hook(self, d):
        if self.stop_evt.is_set():
            raise _Paused()
        title = (d.get("info_dict") or {}).get("title")
        if title and not self.name:
            self.name = title
        if d["status"] == "downloading":
            self.done = d.get("downloaded_bytes") or 0
            self.size = d.get("total_bytes") or d.get("total_bytes_estimate") or self.size
            self.speed = d.get("speed") or 0.0
            if d.get("fragment_count"):
                self.status = f"Téléchargement ({d.get('fragment_index') or 0}/{d['fragment_count']} fragments)"
            else:
                self.status = "Téléchargement"
        elif d["status"] == "finished":
            self.status = "Assemblage…"

    def _run(self):
        try:
            import yt_dlp
        except ImportError:
            self.status = "Erreur : yt-dlp absent (pip install -U yt-dlp)"
            return
        self.status = "Analyse…"
        ffmpeg = shutil.which("ffmpeg")
        audio = self.quality == "Audio MP3"
        fmt = QUALITIES.get(self.quality, QUALITIES["Meilleure"])
        if not ffmpeg and not audio:
            h = re.search(r"height<=(\d+)", fmt)   # sans ffmpeg : flux déjà fusionné uniquement
            fmt = f"b[height<={h.group(1)}]/b" if h else "b"
        opts = {
            "outtmpl": os.path.join(self.folder, "%(title).150B [%(id)s].%(ext)s"),
            "format": fmt,
            "progress_hooks": [self._hook],
            "concurrent_fragment_downloads": self.parts,
            "continuedl": True,
            "noplaylist": True,
            "retries": 10,
            "fragment_retries": 10,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
        }
        if audio and ffmpeg:
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                                       "preferredquality": "0"}]
        if self.browser and self.browser != "Aucun":
            opts["cookiesfrombrowser"] = (self.browser,)
            opts["http_headers"] = {k: v for k, v in self.headers.items() if k != "Cookie"}
        elif self.headers:
            opts["http_headers"] = self.headers
        try:
            os.makedirs(self.folder, exist_ok=True)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
            files = [r["filepath"] for r in (info or {}).get("requested_downloads") or [] if r.get("filepath")]
            if files:
                self.name = os.path.basename(files[-1])
                self.size = self.done = os.path.getsize(files[-1])
            self.status = "Terminé"
        except Exception as e:  # noqa: BLE001
            if self.stop_evt.is_set() and not self.error:
                self.status = "En pause"
                return
            msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "").strip()
            if "DRM" in msg:
                msg = "contenu protégé par DRM, téléchargement impossible"
            self.error = msg
            self.status = f"Erreur : {msg[:150]}"
        finally:
            self.speed = 0.0


def have_ytdlp():
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        return False
    return True


def looks_like_video(url, headers=None):
    """Vrai si l'URL désigne une page de site vidéo / un flux plutôt qu'un fichier direct."""
    if not have_ytdlp():
        return False
    parsed = urllib.parse.urlparse(url)
    if VIDEO_HOSTS.search(parsed.hostname or "") or re.search(r"\.(m3u8|mpd)$", parsed.path, re.I):
        return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {}), "Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            ctype = r.headers.get("Content-Type", "").lower()
    except Exception:  # noqa: BLE001
        return False
    return ctype.startswith("text/html") or "mpegurl" in ctype or "dash+xml" in ctype


def make_download(url, folder, parts=8, quality="Meilleure", browser="Aucun",
                  headers=None, filename=None, kind="auto"):
    """kind : "auto" (détection), "video" (yt-dlp) ou "file" (fichier direct)."""
    if (kind == "video" and have_ytdlp()) or (kind == "auto" and looks_like_video(url, headers)):
        return VideoDownload(url, folder, parts, quality=quality, browser=browser, headers=headers)
    return Download(url, folder, parts, headers=headers, name_hint=filename)


# ---------------------------------------------------------------------------
# Communication avec l'extension du navigateur (socket Unix privée)
# ---------------------------------------------------------------------------
def start_ipc(handler):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        os.unlink(SOCKET_PATH)
    except FileNotFoundError:
        pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o600)
    srv.listen(8)

    def loop():
        while True:
            conn, _ = srv.accept()
            with conn:
                try:
                    reply = handler(json.loads(conn.makefile().readline()))
                except Exception as e:  # noqa: BLE001
                    reply = {"ok": False, "error": str(e)}
                conn.sendall((json.dumps(reply) + "\n").encode())
    threading.Thread(target=loop, daemon=True).start()


def ipc_send(msg, timeout=3):
    """Envoie un message à l'instance PyDM ouverte (OSError si aucune)."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(SOCKET_PATH)
        s.sendall((json.dumps(msg) + "\n").encode())
        return json.loads(s.makefile().readline() or "{}")


# ---------------------------------------------------------------------------
# Ligne de commande
# ---------------------------------------------------------------------------
def run_cli(url, folder, parts, quality="Meilleure", browser="Aucun"):
    d = make_download(url, folder, parts, quality, browser)
    d.start()
    try:
        while d.running:
            time.sleep(0.5)
            pct = f"{100 * d.done / d.size:5.1f} %" if d.size else ""
            eta = human_time((d.size - d.done) / d.speed) if d.size and d.speed else ""
            if isinstance(d, Download):
                extra = f"[{sum(1 for s in d.segments if s[1] < 0 or Download._remaining(s) > 0)} conn.]"
            else:
                extra = d.status
            sys.stdout.write(f"\r{(d.name or '')[:50]}  {pct}  {human(d.done)}/{human(d.size)}  "
                             f"{human(d.speed)}/s  {eta}  {extra}   ")
            sys.stdout.flush()
    except KeyboardInterrupt:
        d.pause()
        d.wait()
    print(f"\n{d.status}" + (f" -> {d.path}" if d.finished else ""))
    if d.status == "En pause":
        print("Relancez la même commande pour reprendre.")
    return 0 if d.finished else 1


# ---------------------------------------------------------------------------
# Interface graphique
# ---------------------------------------------------------------------------
def run_gui(default_dir, parts):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("PyDM – Gestionnaire de téléchargement")
    root.geometry("980x460")
    items = {}  # iid -> Download

    url_var = tk.StringVar()
    dir_var = tk.StringVar(value=default_dir)
    parts_var = tk.IntVar(value=parts)
    clip_var = tk.BooleanVar(value=True)
    quality_var = tk.StringVar(value="Meilleure")
    browser_var = tk.StringVar(value="Aucun")
    dirty = [False]

    def add(url=None, headers=None, filename=None, kind="auto"):
        url = (url or url_var.get()).strip()
        if not re.match(r"^(https?|ftp)://", url):
            messagebox.showwarning("PyDM", "Entrez une URL http(s) ou ftp valide.")
            return
        folder, parts, quality, browser = (os.path.expanduser(dir_var.get()), parts_var.get(),
                                           quality_var.get(), browser_var.get())
        iid = tree.insert("", "end", values=("…",) * 6)
        placeholder = Download(url, folder, parts)
        placeholder.status = "Analyse…"
        items[iid] = placeholder
        url_var.set("")

        def detect():   # fichier direct ou page vidéo ? (réseau : hors du fil de l'interface)
            d = make_download(url, folder, parts, quality, browser, headers, filename, kind)
            if iid in items:
                items[iid] = d
                d.start()
                dirty[0] = True
        threading.Thread(target=detect, daemon=True).start()

    def browse():
        path = filedialog.askdirectory(initialdir=dir_var.get())
        if path:
            dir_var.set(path)

    def selected():
        return [items[i] for i in tree.selection() if i in items]

    def resume():
        for d in selected():
            d.start()

    def pause():
        for d in selected():
            d.pause()

    def remove():
        for iid in tree.selection():
            d = items.pop(iid, None)
            if d:
                d.pause()
            tree.delete(iid)
        save_session()

    def open_folder():
        sel = selected()
        folder = sel[0].folder if sel else os.path.expanduser(dir_var.get())
        subprocess.Popen(["xdg-open", folder])

    def save_session():
        os.makedirs(CONFIG_DIR, exist_ok=True)
        data = []
        for d in list(items.values()):
            e = {"url": d.url, "folder": d.folder, "parts": d.parts, "name": d.name, "headers": d.headers}
            if isinstance(d, VideoDownload):
                e.update(kind="video", quality=d.quality, browser=d.browser)
            data.append(e)
        fd = os.open(SESSION_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # contient des cookies
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=1)

    def load_session():
        try:
            with open(SESSION_FILE) as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        for e in data:
            if e.get("kind") == "video":
                d = VideoDownload(e["url"], e["folder"], e.get("parts", 8), e.get("name"),
                                  e.get("quality", "Meilleure"), e.get("browser", "Aucun"), e.get("headers"))
            else:
                d = Download(e["url"], e["folder"], e.get("parts", 8), e.get("name"), e.get("headers"))
            if d.status == "En attente":
                d.status = "En pause"
            items[tree.insert("", "end", values=("…",) * 6)] = d

    inbox = queue.Queue()

    def show_window():
        root.deiconify()
        root.lift()
        root.attributes("-topmost", True)
        root.after(300, lambda: root.attributes("-topmost", False))

    def handle_inbox():     # messages envoyés par l'extension du navigateur
        while not inbox.empty():
            msg = inbox.get()
            if msg.get("action") == "add" and msg.get("url"):
                add(msg["url"], msg.get("headers"), msg.get("filename"), msg.get("kind", "auto"))
            show_window()

    def refresh():
        handle_inbox()
        if dirty[0]:
            dirty[0] = False
            save_session()
        for iid, d in list(items.items()):
            if not tree.exists(iid):
                continue
            if d.size:
                frac = d.done / d.size
                bar = "█" * int(frac * 12) + "░" * (12 - int(frac * 12))
                prog = f"{bar} {100 * frac:5.1f} %"
            else:
                prog = human(d.done)
            eta = human_time((d.size - d.done) / d.speed) if d.size and d.speed > 0 else ""
            speed = f"{human(d.speed)}/s" if d.running else ""
            tree.item(iid, values=(d.name or d.url, human(d.size), prog, speed, eta, d.status))
        root.after(500, refresh)

    last_clip = [""]

    def watch_clipboard():
        if clip_var.get():
            try:
                text = root.clipboard_get().strip()
            except tk.TclError:
                text = ""
            if text != last_clip[0]:
                last_clip[0] = text
                if re.match(r"^(https?|ftp)://\S+$", text) and not url_var.get():
                    url_var.set(text)
                    root.lift()
        root.after(1000, watch_clipboard)

    def on_close():
        save_session()
        for d in items.values():
            d.pause()
        for d in items.values():
            d.wait(5)
        try:
            os.unlink(SOCKET_PATH)
        except OSError:
            pass
        root.destroy()

    top = ttk.Frame(root, padding=8)
    top.pack(fill="x")
    ttk.Label(top, text="URL :").grid(row=0, column=0, sticky="w")
    entry = ttk.Entry(top, textvariable=url_var)
    entry.grid(row=0, column=1, columnspan=4, sticky="ew", padx=4)
    entry.bind("<Return>", lambda e: add())
    ttk.Button(top, text="Télécharger", command=add).grid(row=0, column=5, sticky="ew")
    ttk.Label(top, text="Dossier :").grid(row=1, column=0, sticky="w", pady=(6, 0))
    ttk.Entry(top, textvariable=dir_var).grid(row=1, column=1, sticky="ew", padx=4, pady=(6, 0))
    ttk.Button(top, text="…", width=3, command=browse).grid(row=1, column=2, pady=(6, 0))
    ttk.Label(top, text="Connexions :").grid(row=1, column=3, padx=(12, 2), pady=(6, 0))
    ttk.Spinbox(top, from_=1, to=32, textvariable=parts_var, width=4).grid(row=1, column=4, pady=(6, 0))
    ttk.Checkbutton(top, text="Surveiller le presse-papiers", variable=clip_var).grid(
        row=1, column=5, padx=(12, 0), pady=(6, 0))
    ttk.Label(top, text="Vidéo :").grid(row=2, column=0, sticky="w", pady=(6, 0))
    opts = ttk.Frame(top)
    opts.grid(row=2, column=1, columnspan=5, sticky="w", padx=4, pady=(6, 0))
    ttk.Combobox(opts, textvariable=quality_var, values=list(QUALITIES), state="readonly",
                 width=11).pack(side="left")
    ttk.Label(opts, text="   Cookies du navigateur :").pack(side="left")
    ttk.Combobox(opts, textvariable=browser_var, values=BROWSERS, state="readonly",
                 width=9).pack(side="left")
    info = ("yt-dlp détecté : sites de streaming pris en charge" if have_ytdlp()
            else "yt-dlp absent : pip install -U yt-dlp pour les sites de streaming")
    if have_ytdlp() and not shutil.which("ffmpeg"):
        info += " (installez ffmpeg pour la meilleure qualité)"
    ttk.Label(opts, text="   " + info, foreground="gray40").pack(side="left")
    top.columnconfigure(1, weight=1)

    cols = (("name", "Fichier", 270), ("size", "Taille", 90), ("prog", "Progression", 220),
            ("speed", "Vitesse", 100), ("eta", "Restant", 80), ("status", "Statut", 160))
    mid = ttk.Frame(root, padding=(8, 0))
    mid.pack(fill="both", expand=True)
    tree = ttk.Treeview(mid, columns=[c[0] for c in cols], show="headings")
    for key, title, width in cols:
        tree.heading(key, text=title)
        tree.column(key, width=width, anchor="w")
    sb = ttk.Scrollbar(mid, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    bottom = ttk.Frame(root, padding=8)
    bottom.pack(fill="x")
    for text, cmd in (("▶ Reprendre", resume), ("⏸ Pause", pause), ("✖ Retirer", remove),
                      ("📂 Ouvrir le dossier", open_folder)):
        ttk.Button(bottom, text=text, command=cmd).pack(side="left", padx=(0, 6))

    load_session()
    try:
        start_ipc(lambda msg: inbox.put(msg) or {"ok": True})
    except OSError as e:
        print(f"Extension du navigateur indisponible : {e}", file=sys.stderr)
    root.protocol("WM_DELETE_WINDOW", on_close)
    refresh()
    watch_clipboard()
    entry.focus()
    root.mainloop()


def main():
    p = argparse.ArgumentParser(description="PyDM - téléchargements multi-connexions")
    p.add_argument("url", nargs="?", help="URL à télécharger (sans URL : interface graphique)")
    p.add_argument("-o", "--output", default=os.path.join(os.path.expanduser("~"), "Téléchargements")
                   if os.path.isdir(os.path.expanduser("~/Téléchargements"))
                   else os.path.expanduser("~/Downloads"), help="dossier de destination")
    p.add_argument("-n", "--connections", type=int, default=8, help="nombre de connexions (défaut 8)")
    p.add_argument("-q", "--qualite", default="Meilleure", choices=list(QUALITIES),
                   help="qualité pour les vidéos de streaming")
    p.add_argument("--cookies", default="Aucun", choices=BROWSERS,
                   help="utiliser les cookies de ce navigateur (vidéos nécessitant votre compte)")
    a = p.parse_args()
    if a.url:
        sys.exit(run_cli(a.url, a.output, a.connections, a.qualite, a.cookies))
    try:
        ipc_send({"action": "show"})    # déjà ouvert : on affiche la fenêtre existante
        return
    except (OSError, ValueError):
        pass
    try:
        import tkinter  # noqa: F401
    except ImportError:
        sys.exit("Tkinter manquant : sudo apt install python3-tk   (ou dnf install python3-tkinter)")
    run_gui(a.output, a.connections)


if __name__ == "__main__":
    main()
