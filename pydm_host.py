#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Hôte de messagerie native : relie l'extension du navigateur à PyDM.

Le navigateur lance ce script et lui passe un message (4 octets de longueur
+ JSON). Il le transmet à PyDM par sa socket Unix, en démarrant PyDM au
besoin, puis renvoie la réponse à l'extension.
"""
import glob
import json
import os
import socket
import struct
import subprocess
import sys
import time

CONFIG_DIR = os.environ.get("PYDM_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".config", "pydm")
SOCKET_PATH = os.path.join(CONFIG_DIR, "pydm.sock")
LAUNCHER = os.path.join(os.path.expanduser("~"), ".local", "bin", "pydm")
YTDLP = os.path.join(os.path.expanduser("~"), ".local", "share", "pydm", "venv", "lib", "python*",
                     "site-packages", "yt_dlp")     # PyDM tourne dans son environnement, pas le Python système
RETRIES = int(os.environ.get("PYDM_HOST_RETRIES") or 60)


def launch_command():
    """PyDM depuis son AppImage (hôte lancé par l'AppImage), sinon le lanceur d'install.sh."""
    appimage = os.environ.get("APPIMAGE")
    return [appimage or LAUNCHER, "--minimized"]


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
    appimage = bool(os.environ.get("APPIMAGE"))
    for _ in range(RETRIES):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect(SOCKET_PATH)
                s.sendall((json.dumps(msg) + "\n").encode())
                return json.loads(s.makefile().readline() or "{}")
        except (FileNotFoundError, ConnectionRefusedError):
            if msg.get("action") == "prefetch":    # simple préparation : jamais de lancement
                return {"ok": False, "error": "PyDM fermé"}
            if not launched:
                if not os.path.exists(command[0]):
                    return {"ok": False, "error": "PyDM introuvable : relancez l'AppImage" if appimage
                            else "PyDM n'est pas installé (lancez install.sh)"}
                subprocess.Popen(command, start_new_session=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                launched = True
            time.sleep(0.25)
    return {"ok": False, "error": "PyDM ne démarre pas" + ("" if appimage else " (relancez install.sh)")}


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
