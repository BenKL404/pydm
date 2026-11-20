#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Hôte de messagerie native : relie l'extension du navigateur à PyDM.

Le navigateur lance ce script et lui passe un message (4 octets de longueur
+ JSON). Il le transmet à PyDM par sa socket Unix, en démarrant PyDM au
besoin, puis renvoie la réponse à l'extension.

Premier message « bridge » : le navigateur a ouvert un port permanent. Ce
processus vit alors aussi longtemps que le port et relaie dans les deux sens,
pour que PyDM puisse à son tour interroger l'extension (cookies à jour).
"""
import getpass
import glob
import hashlib
import json
import ntpath
import os
import queue
import socket
import struct
import subprocess
import sys
import threading
import time

WINDOWS = os.name == "nt"
_ENV_DIR = os.environ.get("PYDM_CONFIG_DIR")
if _ENV_DIR:
    CONFIG_DIR = _ENV_DIR
elif WINDOWS:
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "PyDM")
else:
    CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "pydm")
SOCKET_PATH = os.path.join(CONFIG_DIR, "pydm.sock")
LAUNCHER = os.path.join(os.path.expanduser("~"), ".local", "bin", "pydm")
YTDLP = os.path.join(os.path.expanduser("~"), ".local", "share", "pydm", "venv", "lib", "python*",
                     "site-packages", "yt_dlp")     # PyDM tourne dans son environnement, pas le Python système
KEY_FILE = os.path.join(CONFIG_DIR, "ipc.key")
BREAKAWAY = 0x01000000          # CREATE_BREAKAWAY_FROM_JOB : Firefox tue le « job » de l'hôte à sa sortie
DETACHED = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def default_retries(windows=WINDOWS):
    """Essais de 0,25 s : 15 s, ou 45 s sous Windows (premier lancement lent, antivirus)."""
    return 180 if windows else 60


RETRIES = int(os.environ.get("PYDM_HOST_RETRIES") or default_retries())


def pipe_address(config_dir_env, user):
    """Canal nommé Windows (copie de pydm.ipc.pipe_address)."""
    name = f"pydm-{user}"
    if config_dir_env:
        name += "-" + hashlib.sha1(config_dir_env.encode()).hexdigest()[:8]
    return "\\\\.\\pipe\\" + name


def current_user():
    """Copie de pydm.ipc.current_user."""
    if WINDOWS and os.environ.get("USERNAME"):
        return os.environ["USERNAME"]
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return "user"


def _send(msg):
    """Un échange avec PyDM ; FileNotFoundError ou ConnectionRefusedError s'il n'est pas ouvert,
    TimeoutError s'il démarre, AuthenticationError si le canal n'est pas le sien."""
    if WINDOWS:
        from multiprocessing.connection import Client, answer_challenge, deliver_challenge
        try:
            with open(KEY_FILE, "rb") as f:
                key = f.read()
        except OSError:
            raise FileNotFoundError("PyDM n'a jamais été lancé") from None
        with Client(pipe_address(_ENV_DIR, current_user()), family="AF_PIPE") as conn:
            if not conn.poll(5):
                raise TimeoutError("PyDM ne répond pas")
            answer_challenge(conn, key)             # authentification dans les deux sens (pydm.ipc)
            deliver_challenge(conn, key)
            conn.send_bytes(json.dumps(msg).encode())
            if not conn.poll(5):
                raise TimeoutError("PyDM ne répond pas")
            return json.loads(conn.recv_bytes() or b"{}")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(5)
        s.connect(SOCKET_PATH)
        s.sendall((json.dumps(msg) + "\n").encode())
        return json.loads(s.makefile().readline() or "{}")


class Link:
    """Connexion ouverte vers PyDM ; même interface sous Linux (socket) et Windows (canal)."""

    def __init__(self, conn, stream=None):
        self.conn, self.stream = conn, stream

    def send(self, msg):
        if self.stream is None:
            self.conn.send_bytes(json.dumps(msg).encode())
        else:
            self.conn.sendall((json.dumps(msg) + "\n").encode())

    def messages(self):
        while True:
            if self.stream is None:
                try:
                    raw = self.conn.recv_bytes()
                except (EOFError, OSError):
                    return
            else:
                raw = self.stream.readline()
                if not raw:
                    return
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if isinstance(msg, dict):
                yield msg

    def close(self):
        try:
            self.conn.close()
        except OSError:
            pass


def open_bridge():
    """Ouvre le pont vers PyDM (None s'il n'est pas là : on ne le lance jamais pour un pont)."""
    hello = json.dumps({"action": "bridge"})
    if WINDOWS:
        from multiprocessing.connection import Client, answer_challenge, deliver_challenge
        try:
            with open(KEY_FILE, "rb") as f:
                key = f.read()
            conn = Client(pipe_address(_ENV_DIR, current_user()), family="AF_PIPE")
        except (OSError, ValueError):
            return None
        try:
            if not conn.poll(5):
                raise TimeoutError
            answer_challenge(conn, key)
            deliver_challenge(conn, key)
            conn.send_bytes(hello.encode())
            if not conn.poll(5):
                raise TimeoutError
            conn.recv_bytes()
        except Exception:  # noqa: BLE001 - PyDM absent, occupé ou canal d'un autre compte
            conn.close()
            return None
        return Link(conn)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(5)
        sock.connect(SOCKET_PATH)
        sock.sendall((hello + "\n").encode())
        stream = sock.makefile()
        if not stream.readline():
            raise OSError("pont refusé")
    except OSError:
        sock.close()
        return None
    sock.settimeout(None)
    return Link(sock, stream)


def bridge(connect=open_bridge, pause=1.0, limit=10.0):
    """Port permanent : relaie PyDM → extension et retour, jusqu'à la fermeture du port.

    PyDM peut être fermé quand le navigateur s'ouvre, et s'ouvrir plus tard : on retente, en
    espaçant, sans jamais le lancer — ouvrir un navigateur n'est pas une demande de téléchargement.
    """
    replies, stopped = queue.Queue(), threading.Event()

    def from_extension():
        try:
            while True:
                msg = read_message()
                if msg is None:
                    break
                replies.put(msg)
        except Exception:  # noqa: BLE001 - entrée fermée par le navigateur
            pass
        stopped.set()
    threading.Thread(target=from_extension, daemon=True).start()

    delay = pause
    while not stopped.is_set():
        link = connect()
        if link is None:
            if stopped.wait(delay):
                break
            delay = min(limit, delay * 1.5)
            continue
        delay, broken = pause, threading.Event()

        def to_extension(link=link, broken=broken):
            try:
                for msg in link.messages():
                    send_message(msg)
            except Exception:  # noqa: BLE001 - sortie fermée : le navigateur est parti
                stopped.set()
            finally:
                broken.set()
        threading.Thread(target=to_extension, daemon=True).start()
        while not stopped.is_set() and not broken.is_set():
            try:
                msg = replies.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                link.send(msg)
            except OSError:
                break
        link.close()


def launch_command():
    """PyDM installé sous Windows (pydm.exe à côté de l'hôte), depuis son AppImage, sinon install.sh."""
    if WINDOWS and getattr(sys, "frozen", False):
        return [ntpath.join(ntpath.dirname(sys.executable), "pydm.exe"), "--minimized"]
    appimage = os.environ.get("APPIMAGE")
    return [appimage or LAUNCHER, "--minimized"]


def _spawn(command):
    """Lance PyDM détaché : il survit à l'hôte (et au « job » du navigateur sous Windows)."""
    quiet = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not WINDOWS:
        subprocess.Popen(command, start_new_session=True, **quiet)
        return
    try:
        subprocess.Popen(command, creationflags=DETACHED | BREAKAWAY, **quiet)
    except PermissionError:     # job sans sortie autorisée : lancement simple
        subprocess.Popen(command, creationflags=DETACHED, **quiet)


def read_message():
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    (length,) = struct.unpack("<I", raw)
    return json.loads(sys.stdin.buffer.read(length))


def send_message(obj):
    data = json.dumps(obj).encode()
    sys.stdout.buffer.write(struct.pack("<I", len(data)) + data)
    sys.stdout.buffer.flush()


def forward(msg):
    launched = False
    command = launch_command()
    from multiprocessing import AuthenticationError
    windows_app = WINDOWS and getattr(sys, "frozen", False)
    appimage = bool(os.environ.get("APPIMAGE")) and not windows_app
    packaged = appimage or windows_app
    for _ in range(RETRIES):
        try:
            return _send(msg)
        except (FileNotFoundError, ConnectionRefusedError):
            if msg.get("action") == "prefetch":    # simple préparation : jamais de lancement
                return {"ok": False, "error": "PyDM fermé"}
            if not launched:
                if not os.path.exists(command[0]):
                    return {"ok": False, "error": "PyDM introuvable : relancez l'AppImage" if appimage
                            else "PyDM introuvable : réinstallez PyDM" if windows_app
                            else "PyDM n'est pas installé (lancez install.sh)"}
                _spawn(command)
                launched = True
        except TimeoutError:                # PyDM démarre : on attend sans le relancer
            if msg.get("action") == "prefetch":
                return {"ok": False, "error": "PyDM occupé"}
        except (AuthenticationError, PermissionError) as e:
            return {"ok": False, "error": f"Connexion à PyDM refusée : {e}"}
        time.sleep(0.25)
    return {"ok": False, "error": "PyDM ne démarre pas" + ("" if packaged else " (relancez install.sh)")}


def main():
    msg = read_message()
    if msg is None:
        return
    if msg.get("action") == "ping":
        send_message({"ok": True, "ytdlp": bool(getattr(sys, "frozen", False) or glob.glob(YTDLP))})
    elif msg.get("action") == "bridge":
        bridge()
    else:
        send_message(forward(msg))


if __name__ == "__main__":
    main()
