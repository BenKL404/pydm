import importlib
import json
import os
import socket
import stat
import tempfile
import threading
import unittest
from unittest import mock


class IpcTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"PYDM_CONFIG_DIR": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        import pydm.ipc
        self.ipc = importlib.reload(pydm.ipc)

    def test_aucune_instance(self):
        self.assertFalse(self.ipc.instance_running())

    @unittest.skipIf(os.name == "nt", "socket Unix (POSIX)")
    def test_socket_orpheline(self):
        orphan = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        orphan.bind(self.ipc.SOCKET_PATH)
        orphan.close()
        self.assertTrue(os.path.exists(self.ipc.SOCKET_PATH))
        self.assertFalse(self.ipc.instance_running())
        self.ipc.start_ipc(lambda msg: {"ok": True})
        self.assertEqual(self.ipc.ipc_send({"action": "ping"}), {"ok": True})
        self.assertEqual(stat.S_IMODE(os.stat(self.ipc.SOCKET_PATH).st_mode), 0o600)


    def test_adresse_canal(self):
        pipe = self.ipc.pipe_address
        self.assertEqual(pipe(None, "Élodie Durand"), "\\\\.\\pipe\\pydm-Élodie Durand")
        a, b = pipe("C:\\tests\\a", "u"), pipe("C:\\tests\\b", "u")
        self.assertRegex(a, r"^\\\\\.\\pipe\\pydm-u-[0-9a-f]{8}$")
        self.assertNotEqual(a, b)
        self.assertEqual(a, pipe("C:\\tests\\a", "u"))

    @unittest.skipUnless(os.name == "nt", "canal nommé (Windows)")
    def test_aller_retour_windows(self):
        self.ipc.start_ipc(lambda m: {"ok": True, "echo": m.get("x")})
        self.assertEqual(self.ipc.ipc_send({"x": "é"}), {"ok": True, "echo": "é"})
        self.assertTrue(self.ipc.instance_running())
        with tempfile.TemporaryDirectory() as other, mock.patch.dict(os.environ, {"PYDM_CONFIG_DIR": other}):
            import pydm.ipc
            self.assertFalse(importlib.reload(pydm.ipc).instance_running())
        importlib.reload(pydm.ipc)

    def test_poignee_de_main(self):
        import threading
        from multiprocessing import AuthenticationError
        from multiprocessing.connection import Pipe
        for client_key, ok in ((b"k" * 32, True), (b"x" * 32, False)):
            a, b = Pipe()
            result = {}

            def server():
                try:
                    self.ipc.server_handshake(a, b"k" * 32)
                    result["server"] = True
                except (AuthenticationError, EOFError, OSError):
                    result["server"] = False
                    a.close()
            t = threading.Thread(target=server)
            t.start()
            if ok:
                self.ipc.client_handshake(b, client_key)
            else:
                with self.assertRaises((AuthenticationError, EOFError, OSError)):
                    self.ipc.client_handshake(b, client_key)
                b.close()
            t.join(5)
            self.assertEqual(result["server"], ok)

    def test_cle_privee(self):
        self.assertIsNone(self.ipc.load_key(create=False))
        key = self.ipc.load_key(create=True)
        self.assertEqual(len(key), 32)
        self.assertEqual(self.ipc.load_key(create=False), key)
        self.assertEqual(self.ipc.load_key(create=True), key)

    def test_nom_utilisateur_windows(self):
        with mock.patch.dict(os.environ, {"USERNAME": "Élodie", "USER": "msys", "LOGNAME": "msys"}):
            self.assertEqual(self.ipc.current_user(windows=True), "Élodie")

    def test_verrou_instance(self):
        class Kernel32:
            def __init__(self, err):
                self.err, self.names = err, []

            def CreateMutexW(self, attrs, owner, name):
                self.names.append(name)
                return 42

            def GetLastError(self):
                return self.err
        free, taken = Kernel32(0), Kernel32(183)            # 183 : ERROR_ALREADY_EXISTS
        self.assertTrue(self.ipc.acquire_instance_lock(kernel32=free))
        self.assertFalse(self.ipc.acquire_instance_lock(kernel32=taken))
        self.assertRegex(free.names[0], r"^PyDM-instance-[0-9a-f]{8}$")      # dossier de test : verrou à part
        self.assertEqual(self.ipc.mutex_name(None), "PyDM-instance")

class BridgeTest(unittest.TestCase):
    """Pont persistant : PyDM interroge l'extension et reçoit sa réponse par la même connexion."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"PYDM_CONFIG_DIR": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        import pydm.ipc
        self.ipc = importlib.reload(pydm.ipc)
        self.addCleanup(lambda: importlib.reload(pydm.ipc))
        self.ipc.start_ipc(lambda msg: {"ok": True, "echo": msg.get("x")})

    def open_bridge(self):
        """Côté hôte natif : ouvre le pont et renvoie (lire_une_demande, répondre, fermer)."""
        if os.name == "nt":
            from multiprocessing.connection import Client
            conn = Client(self.ipc.PIPE_ADDRESS, family="AF_PIPE")
            conn.poll(5)
            self.ipc.client_handshake(conn, self.ipc.load_key())
            conn.send_bytes(json.dumps({"action": "bridge"}).encode())
            json.loads(conn.recv_bytes())
            self.addCleanup(conn.close)
            return (lambda t=5: json.loads(conn.recv_bytes()) if conn.poll(t) else None,
                    lambda msg: conn.send_bytes(json.dumps(msg).encode()), conn.close)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self.ipc.SOCKET_PATH)
        self.addCleanup(sock.close)
        f = sock.makefile()
        sock.sendall(b'{"action": "bridge"}\n')
        self.assertEqual(json.loads(f.readline()), {"ok": True})

        def ask(timeout=5):
            sock.settimeout(timeout)
            try:
                return json.loads(f.readline() or "null")
            except socket.timeout:
                return None
        def close():
            f.close()           # makefile garde le descripteur : fermer la socket ne suffit pas
            sock.close()
        return ask, lambda msg: sock.sendall((json.dumps(msg) + "\n").encode()), close

    def request(self, **kw):
        """Lance ipc.request dans un fil (il attend la réponse de l'extension)."""
        out = {}

        def run():
            try:
                out["reply"] = self.ipc.request("refresh", **kw)
            except Exception as e:  # noqa: BLE001
                out["error"] = e
        t = threading.Thread(target=run, daemon=True)
        t.start()
        return out, t

    def test_aller_retour(self):
        ask, answer, _ = self.open_bridge()
        out, t = self.request(url="https://a.fr/f.bin", referer="https://a.fr/p")
        demande = ask()
        self.assertEqual(demande["action"], "refresh")
        self.assertEqual((demande["url"], demande["referer"]), ("https://a.fr/f.bin", "https://a.fr/p"))
        self.assertTrue(demande["id"])
        answer({"id": demande["id"], "headers": {"Cookie": "SID=2", "User-Agent": "Firefox"}})
        t.join(5)
        self.assertEqual(out.get("reply", {}).get("headers"), {"Cookie": "SID=2", "User-Agent": "Firefox"})

    def test_sans_pont(self):
        with self.assertRaises(OSError):
            self.ipc.request("refresh", url="https://a.fr/f.bin")

    def test_erreur_de_l_extension(self):
        ask, answer, _ = self.open_bridge()
        out, t = self.request(url="https://a.fr/f.bin")
        answer({"id": ask()["id"], "error": "no-tab"})
        t.join(5)
        self.assertIsInstance(out.get("error"), self.ipc.BridgeError)
        self.assertIn("no-tab", str(out["error"]))

    def test_delai_depasse(self):
        ask, _, _ = self.open_bridge()
        out, t = self.request(url="https://a.fr/f.bin", timeout=0.3)
        ask()
        t.join(5)
        self.assertIsInstance(out.get("error"), TimeoutError)

    def test_reponse_inconnue_ignoree(self):
        ask, answer, _ = self.open_bridge()
        out, t = self.request(url="https://a.fr/f.bin")
        demande = ask()
        answer({"id": "jamais-demandé", "headers": {"Cookie": "x"}})
        answer({"pas": "un identifiant"})
        answer({"id": demande["id"], "headers": {"Cookie": "bon"}})
        t.join(5)
        self.assertEqual(out["reply"]["headers"], {"Cookie": "bon"})

    def test_deux_demandes_en_parallele(self):
        ask, answer, _ = self.open_bridge()
        a, ta = self.request(url="https://a.fr/1")
        b, tb = self.request(url="https://a.fr/2")
        d1, d2 = ask(), ask()
        par_url = {d["url"]: d["id"] for d in (d1, d2)}
        self.assertEqual(len(par_url), 2)
        answer({"id": par_url["https://a.fr/2"], "headers": {"Cookie": "deux"}})      # désordre
        answer({"id": par_url["https://a.fr/1"], "headers": {"Cookie": "un"}})
        ta.join(5), tb.join(5)
        self.assertEqual((a["reply"]["headers"], b["reply"]["headers"]),
                         ({"Cookie": "un"}, {"Cookie": "deux"}))

    def test_pont_ferme_pendant_la_demande(self):
        ask, _, close = self.open_bridge()
        out, t = self.request(url="https://a.fr/f.bin")
        ask()
        close()
        t.join(5)
        self.assertFalse(t.is_alive(), "la demande doit échouer dès la rupture du pont")
        self.assertIsInstance(out.get("error"), OSError)

    def test_messages_ordinaires_toujours_servis(self):
        """Un pont ouvert ne doit pas monopoliser la boucle d'écoute."""
        self.open_bridge()
        self.assertEqual(self.ipc.ipc_send({"action": "ping", "x": "é"}), {"ok": True, "echo": "é"})


if __name__ == "__main__":
    unittest.main()
