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
RETRIES = int(os.environ.get("PYDM_HOST_RETRIES") or 60)


def pipe_address(config_dir_env, user):
    """Canal nommé Windows (copie de pydm.ipc.pipe_address)."""
    name = f"pydm-{user}"
    if config_dir_env:
        name += "-" + hashlib.sha1(config_dir_env.encode()).hexdigest()[:8]
    return "\\\\.\\pipe\\" + name


def _send(msg):
    """Un échange avec PyDM ; FileNotFoundError ou ConnectionRefusedError s'il n'est pas ouvert."""
    if WINDOWS:
        from multiprocessing.connection import Client
        try:
            user = getpass.getuser()
        except Exception:  # noqa: BLE001
            user = "user"
        with Client(pipe_address(_ENV_DIR, user), family="AF_PIPE") as conn:
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


def _detached():
    """Options de lancement : PyDM survit à l'hôte, sans fenêtre console sous Windows."""
    if WINDOWS:
        return {"creationflags": 0x00000008 | 0x00000200}    # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    return {"start_new_session": True}


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
    packaged = bool(os.environ.get("APPIMAGE")) or (WINDOWS and getattr(sys, "frozen", False))
    for _ in range(RETRIES):
        try:
            return _send(msg)
        except (FileNotFoundError, ConnectionRefusedError):
            if msg.get("action") == "prefetch":    # simple préparation : jamais de lancement
                return {"ok": False, "error": "PyDM fermé"}
            if not launched:
                if not os.path.exists(command[0]):
                    return {"ok": False, "error": "PyDM introuvable : réinstallez PyDM" if packaged
                            else "PyDM n'est pas installé (lancez install.sh)"}
                subprocess.Popen(command, **_detached(),
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                launched = True
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
