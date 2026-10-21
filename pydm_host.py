#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Hôte de messagerie native : relie l'extension du navigateur à PyDM.

Le navigateur lance ce script et lui passe un message (4 octets de longueur
+ JSON). Il le transmet à PyDM par sa socket Unix, en démarrant PyDM au
besoin, puis renvoie la réponse à l'extension.
"""
import getpass
import glob
import hashlib
import json
import ntpath
import os
import socket
import struct
import subprocess
import sys
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
    else:
        send_message(forward(msg))


if __name__ == "__main__":
    main()
