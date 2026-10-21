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

if __name__ == "__main__":
    unittest.main()
