# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Communication avec l'extension du navigateur et entre instances.

Linux : socket Unix privée. Windows : canal nommé propre à l'utilisateur. Un échange = un message
JSON et sa réponse. Transport recopié dans pydm_host.py (qui reste autonome).
"""
import getpass
import hashlib
import json
import os
import socket
import threading

WINDOWS = os.name == "nt"
_ENV_DIR = os.environ.get("PYDM_CONFIG_DIR")
if _ENV_DIR:
    CONFIG_DIR = _ENV_DIR
elif WINDOWS:
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "PyDM")
else:
    CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "pydm")
SOCKET_PATH = os.path.join(CONFIG_DIR, "pydm.sock")


def pipe_address(config_dir_env, user):
    """Canal nommé Windows ; un dossier de réglages imposé (tests) a son propre canal."""
    name = f"pydm-{user}"
    if config_dir_env:
        name += "-" + hashlib.sha1(config_dir_env.encode()).hexdigest()[:8]
    return "\\\\.\\pipe\\" + name


def _user():
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 (aucune variable d'utilisateur)
        return "user"


PIPE_ADDRESS = pipe_address(_ENV_DIR, _user())


def _reply(handler, data):
    try:
        return handler(json.loads(data))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def start_ipc(handler):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if WINDOWS:
        from multiprocessing.connection import Listener
        listener = Listener(PIPE_ADDRESS, family="AF_PIPE")

        def loop():
            while True:
                try:
                    conn = listener.accept()
                except OSError:
                    continue
                with conn:
                    try:
                        conn.send_bytes(json.dumps(_reply(handler, conn.recv_bytes())).encode())
                    except (OSError, EOFError):
                        pass
        threading.Thread(target=loop, daemon=True).start()
        return
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
                reply = _reply(handler, conn.makefile().readline())
                conn.sendall((json.dumps(reply) + "\n").encode())
    threading.Thread(target=loop, daemon=True).start()


def ipc_send(msg, timeout=3):
    """Envoie un message à l'instance PyDM ouverte (OSError si aucune)."""
    if WINDOWS:
        from multiprocessing.connection import Client
        with Client(PIPE_ADDRESS, family="AF_PIPE") as conn:     # FileNotFoundError si aucun canal
            conn.send_bytes(json.dumps(msg).encode())
            if not conn.poll(timeout):
                raise TimeoutError("PyDM ne répond pas")
            return json.loads(conn.recv_bytes() or b"{}")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(SOCKET_PATH)
        s.sendall((json.dumps(msg) + "\n").encode())
        return json.loads(s.makefile().readline() or "{}")


def instance_running():
    """Vrai si une instance PyDM ouverte répond."""
    try:
        ipc_send({"action": "show"})
    except (OSError, EOFError, ValueError):
        return False
    return True
