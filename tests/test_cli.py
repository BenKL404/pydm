import os
import subprocess
import sys
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
