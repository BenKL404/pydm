# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Communication avec l'extension du navigateur et entre instances (socket Unix privée)."""
import json
import os
import socket
import threading

CONFIG_DIR = os.environ.get("PYDM_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".config", "pydm")
SOCKET_PATH = os.path.join(CONFIG_DIR, "pydm.sock")


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


def instance_running():
    """Vrai si une instance PyDM ouverte répond sur la socket."""
    try:
        ipc_send({"action": "show"})
    except (OSError, ValueError):
        return False
    return True
