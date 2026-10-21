# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Moteur de téléchargement : fichiers directs multi-connexions et vidéos via yt-dlp."""
import glob
import json
import os
import re
import shutil
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from email.message import Message

from .filetypes import category
from .scheduler import LIMITER
from .util import safe_filename, unique_path

CHUNK = 64 * 1024
MIN_SPLIT = 2 * 1024 * 1024
MAX_RETRIES = 6
UA = "Mozilla/5.0 (X11; Linux x86_64) PyDM/1.0"
_NAMES = threading.Lock()     # choix du nom + création du .part : atomique entre téléchargements
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
    name = safe_filename(name)
    return size, ranges, name


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
    def __init__(self, url, folder, parts=8, name=None, headers=None, name_hint=None, route=None):
        self.url = url
        self.folder = folder
        self.route = route      # catégorie → dossier, appliqué quand le nom est connu (nouveau téléchargement)
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
        self.added = time.time()
        self.want = "now"      # now, later, force, stop (voir scheduler)
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

    @property
    def active_connections(self):
        if not self.running:
            return 0
        return sum(1 for s in self.segments if s[1] < 0 or self._remaining(s) > 0)

    @property
    def resumable(self):
        return self.ranges

    def files(self):
        """Fichiers présents sur le disque pour ce téléchargement."""
        if not self.name:
            return []
        return [p for p in (self.path, self.part_path, self.state_path) if os.path.exists(p)]

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
        if not self.name and self.route:
            self.folder = self.route(category(self.name_hint or name))
        os.makedirs(self.folder, exist_ok=True)
        if self.segments and self.size == size and self.ranges == ranges and os.path.exists(self.part_path):
            if not ranges:      # pas de reprise possible sans plages : on recommence
                self.segments = [[0, size - 1 if size else -1, 0]]
                open(self.part_path, "wb").close()
            return
        if not self.name:
            with _NAMES:
                self.name = name
                if self._load_state() and self.size == size:
                    return
                self.name = unique_path(self.folder, name)
                open(self.part_path, "wb").close()      # réserve le nom
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
                        LIMITER.consume(len(buf), self.stop_evt)
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
            self.error = friendly_error(str(e))
            self.status = f"Erreur : {self.error}"
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
        try:
            os.replace(self.part_path, self.path)
        except OSError as e:
            self.error = str(e)
            self.status = f"Erreur : {e}"
            return
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
                 headers=None, fmt=None, stem=None):
        self.url = url
        self.fmt = fmt          # sélecteur yt-dlp choisi dans la fenêtre d'ajout
        self.stem = stem        # nom choisi, sans extension
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
        self.added = time.time()
        self.want = "now"      # now, later, force, stop (voir scheduler)
        self.stop_evt = threading.Event()
        self._rate_lock = threading.Lock()
        self._last_bytes = self._last_file = None
        self.status = "Terminé" if name and os.path.exists(self.path) else (
            "En pause" if name else "En attente")

    def _safe_stem(self):
        """Nom choisi, tronqué à 150 octets puis rendu valide ("" : nom donné par yt-dlp)."""
        raw = (self.stem or "").strip().encode()[:150].decode(errors="ignore")
        return safe_filename(raw, fallback="")

    @property
    def path(self):
        return os.path.join(self.folder, self.name or "")

    active_connections = 0
    resumable = True

    def files(self):
        """Fichier final et fichiers intermédiaires de yt-dlp (.fNNN, .part, .ytdl…)."""
        if self.name:
            base, own = os.path.splitext(self.path)[0], [self.path, self.path + ".part", self.path + ".ytdl"]
        elif self._safe_stem():
            base, own = os.path.join(self.folder, self._safe_stem()), []
        else:
            return []
        b = glob.escape(base)
        found = set(own)
        for pattern in (".f[0-9]*", ".*.part", ".*.ytdl", ".temp.*", ".*.part-Frag*"):
            found.update(glob.glob(b + pattern))
        return sorted(p for p in found if os.path.isfile(p))

    def _hook(self, d):
        if self.stop_evt.is_set():
            raise _Paused()
        title = (d.get("info_dict") or {}).get("title")
        if title and not self.name:
            self.name = title
        if d["status"] == "downloading":
            got = d.get("downloaded_bytes") or 0
            with self._rate_lock:       # yt-dlp appelle le hook depuis plusieurs threads
                if self._last_bytes is None or d.get("filename") != self._last_file:
                    # début (déjà sur le disque en cas de reprise) ou fichier suivant : rien à freiner
                    self._last_file, self._last_bytes, delta = d.get("filename"), got, 0
                else:                   # les fragments peuvent arriver dans le désordre
                    delta = got - self._last_bytes
                    self._last_bytes = max(self._last_bytes, got)
            if delta > 0:
                LIMITER.consume(delta, self.stop_evt)
            self.done = got
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
            self.error = "yt-dlp absent (relancez install.sh)"
            self.status = f"Erreur : {self.error}"
            return
        self._last_bytes = None             # premier relevé = point de départ (reprise)
        self.status = "Analyse…"
        ffmpeg = shutil.which("ffmpeg")
        audio = self.quality == "Audio MP3"
        fmt = QUALITIES.get(self.quality, QUALITIES["Meilleure"])
        if not ffmpeg and not audio:
            h = re.search(r"height<=(\d+)", fmt)   # sans ffmpeg : flux déjà fusionné uniquement
            fmt = f"b[height<={h.group(1)}]/b" if h else "b"
        if self.fmt and self.fmt != fmt:            # format choisi, repli si YouTube l'a retiré
            fmt = f"{self.fmt}/{fmt}"
        stem = self._safe_stem()
        opts = {
            "outtmpl": os.path.join(self.folder, (stem.replace("%", "%%") or "%(title).150B [%(id)s]")
                                    + ".%(ext)s"),
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
        opts["http_headers"] = {k: v for k, v in self.headers.items() if k != "Cookie"}
        try:
            os.makedirs(self.folder, exist_ok=True)
        except OSError as e:
            self.error = str(e)
            self.status = f"Erreur : {e}"
            return
        first_error = None
        attempts = ytdlp_attempts(self.url, self.headers, self.browser)
        try:
            for extra in attempts:
                if extra:
                    self.status = "Nouvel essai avec vos cookies…"
                try:
                    with yt_dlp.YoutubeDL({**opts, **extra}) as ydl:
                        info = ydl.extract_info(self.url, download=True)
                    files = [r["filepath"] for r in (info or {}).get("requested_downloads") or []
                             if r.get("filepath")]
                    if files:
                        self.name = os.path.basename(files[-1])
                        self.size = self.done = os.path.getsize(files[-1])
                    self.status = "Terminé"
                    return
                except Exception as e:  # noqa: BLE001
                    if self.stop_evt.is_set() and not self.error:
                        self.status = "En pause"
                        return
                    first_error = first_error or e
                finally:
                    self.speed = 0.0
        finally:
            attempts.close()        # supprime le fichier de cookies éventuel
        msg = re.sub(r"\x1b\[[0-9;]*m", "", str(first_error)).replace("ERROR: ", "").strip()
        if "DRM" in msg:
            msg = "contenu protégé par DRM, téléchargement impossible"
        msg = friendly_error(msg)
        self.error = msg
        self.status = f"Erreur : {msg[:150]}"


def ytdlp_attempts(url, headers, browser):
    """Options yt-dlp de chaque essai : d'abord sans cookies, puis avec s'il y en a.

    Avec une session YouTube connectée, yt-dlp échoue (« The page needs to be reloaded ») même
    sur des vidéos publiques : les cookies (navigateur choisi, sinon ceux de l'extension, passés
    par un fichier) ne servent qu'en second essai. Le fichier est supprimé à la fermeture.
    """
    yield {}
    if browser and browser != "Aucun":
        yield {"cookiesfrombrowser": (browser,)}
    elif (headers or {}).get("Cookie"):
        path = _cookie_file(url, headers["Cookie"])
        try:
            yield {"cookiefile": path}
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


def friendly_error(msg, windows=(os.name == "nt")):
    """Message lisible pour les refus courants (le détail technique reste à la fin)."""
    low = msg.lower()
    if windows and ("dpapi" in low or ("cookie" in low and "decrypt" in low)):
        return ("Chrome chiffre ses cookies sous Windows d'une façon que PyDM ne peut pas lire : choisissez "
                "Firefox dans « Cookies ». — " + msg)
    if "HTTP Error 403" in msg:
        return ("Accès refusé par le serveur (403) : le lien est peut-être lié au navigateur ou à son "
                "adresse IP (VPN ou proxy ?), ou a expiré. Rechargez la page puis renvoyez le lien. — " + msg)
    return msg


def clean_stale_cookie_files(max_age=3600, tmpdir=None):
    """Supprime les fichiers de cookies temporaires oubliés (PyDM quitté pendant une analyse)."""
    now = time.time()
    for path in glob.glob(os.path.join(tmpdir or tempfile.gettempdir(), "pydm-cookies-*.txt")):
        try:
            if now - os.path.getmtime(path) > max_age:
                os.remove(path)
        except OSError:
            pass


def _cookie_file(url, header):
    """Écrit l'en-tête Cookie au format Netscape (celui de yt-dlp), pour le domaine du lien."""
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    for prefix in ("www.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix):]
            break
    secure = "TRUE" if parsed.scheme == "https" else "FALSE"
    fd, path = tempfile.mkstemp(prefix="pydm-cookies-", suffix=".txt")     # créé en 0600
    with os.fdopen(fd, "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for part in header.split(";"):
            name, sep, value = part.strip().partition("=")
            if sep and name:
                f.write(f".{host}\tTRUE\t/\t{secure}\t0\t{name}\t{value}\n")
    return path


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
                  headers=None, filename=None, kind="auto", fmt=None, stem=None, route=None):
    """kind : "auto" (détection), "video" (yt-dlp) ou "file" (fichier direct)."""
    if (kind == "video" and have_ytdlp()) or (kind == "auto" and looks_like_video(url, headers)):
        if route:
            folder = route("music" if quality == "Audio MP3" else "video")
        return VideoDownload(url, folder, parts, quality=quality, browser=browser, headers=headers,
                             fmt=fmt, stem=stem)
    return Download(url, folder, parts, headers=headers, name_hint=filename, route=route)


def entry_from_task(t):
    """Entrée de session (format JSON) décrivant la tâche."""
    e = {"url": t.url, "folder": t.folder, "parts": t.parts, "name": t.name, "headers": t.headers,
         "added": datetime.fromtimestamp(t.added).isoformat(timespec="seconds"),
         "want": "stop" if t.finished else t.want}     # un fichier terminé puis déplacé n'est pas repris
    if isinstance(t, VideoDownload):
        e.update(kind="video", quality=t.quality, browser=t.browser, fmt=t.fmt, stem=t.stem)
    return e


def task_from_entry(e):
    """Recrée la tâche d'une entrée de session (les anciennes entrées n'ont pas « added »)."""
    if e.get("kind") == "video":
        t = VideoDownload(e["url"], e["folder"], e.get("parts", 8), e.get("name"),
                          e.get("quality", "Meilleure"), e.get("browser", "Aucun"), e.get("headers"),
                          e.get("fmt"), e.get("stem"))
    else:
        t = Download(e["url"], e["folder"], e.get("parts", 8), e.get("name"), e.get("headers"))
    want = e.get("want")
    t.want = "now" if want in ("now", "force") else ("later" if want == "later" else "stop")
    try:
        t.added = datetime.fromisoformat(e["added"]).timestamp()
    except (KeyError, TypeError, ValueError):
        pass
    return t
