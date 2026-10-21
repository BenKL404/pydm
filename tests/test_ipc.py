import importlib
import os
import socket
import stat
import tempfile
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

if __name__ == "__main__":
    unittest.main()
