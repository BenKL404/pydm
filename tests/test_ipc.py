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

    def test_socket_orpheline(self):
        orphan = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        orphan.bind(self.ipc.SOCKET_PATH)
        orphan.close()
        self.assertTrue(os.path.exists(self.ipc.SOCKET_PATH))
        self.assertFalse(self.ipc.instance_running())
        self.ipc.start_ipc(lambda msg: {"ok": True})
        self.assertEqual(self.ipc.ipc_send({"action": "ping"}), {"ok": True})
        self.assertEqual(stat.S_IMODE(os.stat(self.ipc.SOCKET_PATH).st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
