# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Communication avec l'extension du navigateur et entre instances.

Linux : socket Unix privée. Windows : canal nommé propre à l'utilisateur, avec authentification
dans les deux sens par une clé privée (%APPDATA%\\PyDM\\ipc.key) : un autre compte qui occuperait le
nom du canal ne reçoit rien. Un échange = un message JSON et sa réponse. Transport recopié dans
pydm_host.py (qui reste autonome).
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


def current_user(windows=WINDOWS):
    """Nom de l'utilisateur ; sous Windows USERNAME d'abord (un shell MSYS peut définir USER)."""
    if windows and os.environ.get("USERNAME"):
        return os.environ["USERNAME"]
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 (aucune variable d'utilisateur)
        return "user"


PIPE_ADDRESS = pipe_address(_ENV_DIR, current_user())
KEY_FILE = os.path.join(CONFIG_DIR, "ipc.key")
_LOCK = []                  # poignée du verrou d'instance, gardée jusqu'à la fin du processus


def mutex_name(config_dir_env):
    """Verrou d'instance Windows (aussi vérifié par l'installateur : AppMutex)."""
    name = "PyDM-instance"
    if config_dir_env:
        name += "-" + hashlib.sha1(config_dir_env.encode()).hexdigest()[:8]
    return name


def acquire_instance_lock(kernel32=None):
    """Windows : vrai si ce processus est le seul PyDM (verrou pris dès le lancement)."""
    if kernel32 is None:
        import ctypes
        dll = ctypes.WinDLL("kernel32", use_last_error=True)
        handle, error = dll.CreateMutexW(None, False, mutex_name(_ENV_DIR)), ctypes.get_last_error()
    else:
        handle = kernel32.CreateMutexW(None, False, mutex_name(_ENV_DIR))
        error = kernel32.GetLastError()
    if not handle:
        return True             # verrou impossible : on ne bloque pas le démarrage
    _LOCK.append(handle)
    return error != 183         # ERROR_ALREADY_EXISTS


def load_key(create=False):
    """Clé privée du canal (32 octets) ; créée par PyDM au besoin. None si absente."""
    try:
        with open(KEY_FILE, "rb") as f:
            key = f.read()
        if len(key) == 32:
            return key
    except OSError:
        pass
    if not create:
        return None
    os.makedirs(CONFIG_DIR, exist_ok=True)
    key, tmp = os.urandom(32), f"{KEY_FILE}.tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
        f.write(key)
    os.replace(tmp, KEY_FILE)
    return key


def server_handshake(conn, key):
    from multiprocessing.connection import answer_challenge, deliver_challenge
    deliver_challenge(conn, key)
    answer_challenge(conn, key)


def client_handshake(conn, key):
    from multiprocessing.connection import answer_challenge, deliver_challenge
    answer_challenge(conn, key)
    deliver_challenge(conn, key)


def _reply(handler, data):
    try:
        return handler(json.loads(data))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def start_ipc(handler):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if WINDOWS:
        from multiprocessing import AuthenticationError
        from multiprocessing.connection import Listener
        key = load_key(create=True)
        listener = Listener(PIPE_ADDRESS, family="AF_PIPE")

        def serve(conn):            # un fil par client : un client muet ne bloque pas les autres
            with conn:
                try:
                    server_handshake(conn, key)
                    if conn.poll(5):
                        conn.send_bytes(json.dumps(_reply(handler, conn.recv_bytes())).encode())
                except (OSError, EOFError, AuthenticationError):
                    pass

        def loop():
            while True:
                try:
                    conn = listener.accept()
                except OSError:
                    continue
                threading.Thread(target=serve, args=(conn,), daemon=True).start()
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
        key = load_key()
        if key is None:
            raise FileNotFoundError("PyDM n'a jamais été lancé")
        with Client(PIPE_ADDRESS, family="AF_PIPE") as conn:     # FileNotFoundError si aucun canal
            if not conn.poll(timeout):              # canal créé, PyDM pas encore prêt
                raise TimeoutError("PyDM ne répond pas")
            client_handshake(conn, key)
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
    from multiprocessing import AuthenticationError
    try:
        ipc_send({"action": "show"})
    except (OSError, EOFError, ValueError, AuthenticationError):
        return False
    return True
