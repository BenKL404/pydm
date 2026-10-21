import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CliTest(unittest.TestCase):
    def test_help(self):
        r = subprocess.run([sys.executable, "-m", "pydm", "--help"], cwd=ROOT,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--connections", r.stdout)

    def test_connexions_hors_bornes(self):
        r = subprocess.run([sys.executable, "-m", "pydm", "-n", "100", "https://a.fr/x"], cwd=ROOT,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 2)
        self.assertIn("1 et 32", r.stderr)

    def test_sans_pyside6(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = os.path.join(tmp, "PySide6")
            os.mkdir(fake)
            with open(os.path.join(fake, "__init__.py"), "w") as f:
                f.write("raise ImportError('PySide6 simulé absent')\n")
            env = dict(os.environ, PYTHONPATH=os.pathsep.join([tmp, ROOT]),
                       PYDM_CONFIG_DIR=os.path.join(tmp, "cfg"))
            r = subprocess.run([sys.executable, "-m", "pydm"], cwd=ROOT, env=env,
                               capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 1)
        self.assertIn("Interface indisponible : PySide6 n'est pas installé. Relancez ./install.sh", r.stderr)


    def test_native_host_arguments_navigateur(self):
        from pydm import cli
        sys.path.insert(0, ROOT)
        for args in (["/x/com.pydm.host.json", "pydm@local"],
                     ["chrome-extension://feloklndigmnjlmffbddgcdfigpnbcba/", "--parent-window=0"]):
            with mock.patch("pydm_host.main") as host:
                cli.main(["--native-host", *args])
            host.assert_called_once_with()

    def test_native_host_ping_reel(self):
        raw = json.dumps({"action": "ping"}).encode()
        r = subprocess.run([sys.executable, "-m", "pydm", "--native-host", "chrome-extension://x/"], cwd=ROOT,
                           input=struct.pack("<I", len(raw)) + raw, capture_output=True, timeout=30)
        self.assertTrue(json.loads(r.stdout[4:])["ok"], r.stderr)

    def test_environnement_fige(self):
        from pydm.cli import prepare_frozen_env
        env = {"PATH": "/usr/bin", "LD_LIBRARY_PATH": "/tmp/_MEI/lib", "LD_LIBRARY_PATH_ORIG": "/opt/lib"}
        prepare_frozen_env(env, "/app/usr/bin/_internal")      # dossier des binaires livrés (sys._MEIPASS)
        self.assertEqual(env["PATH"], "/app/usr/bin/_internal:/usr/bin")
        self.assertEqual(env["LD_LIBRARY_PATH"], "/opt/lib")
        env = {"PATH": "/usr/bin", "LD_LIBRARY_PATH": "/tmp/_MEI/lib"}
        prepare_frozen_env(env, "/app/usr/bin/_internal")
        self.assertNotIn("LD_LIBRARY_PATH", env)

if __name__ == "__main__":
    unittest.main()
