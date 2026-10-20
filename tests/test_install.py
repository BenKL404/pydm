import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def have_venv():
    with tempfile.TemporaryDirectory() as d:
        return subprocess.run([sys.executable, "-m", "venv", "--without-pip", d],
                              capture_output=True).returncode == 0


@unittest.skipUnless(have_venv(), "python3 -m venv indisponible")
class InstallTest(unittest.TestCase):
    def test_install_home_temporaire(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, HOME=home, PYDM_SKIP_PIP="1")
            env.pop("PYDM_CONFIG_DIR", None)
            for _ in range(2):      # le second lancement doit aussi réussir
                r = subprocess.run(["sh", os.path.join(ROOT, "install.sh")], env=env,
                                   capture_output=True, text=True, timeout=300)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            j = lambda *p: os.path.join(home, *p)  # noqa: E731
            launcher = j(".local/bin/pydm")
            self.assertTrue(os.access(launcher, os.X_OK))
            self.assertTrue(os.path.exists(j(".local/share/pydm/pydm/engine.py")))
            self.assertTrue(os.path.exists(j(".local/share/pydm/venv/bin/python")))
            with open(j(".mozilla/native-messaging-hosts/com.pydm.host.json")) as f:
                self.assertTrue(json.load(f)["path"].endswith("pydm_host.py"))
            with open(j(".local/share/applications/pydm.desktop")) as f:
                desktop = f.read()
            self.assertIn(f'Exec="{home}/.local/bin/pydm"', desktop)
            self.assertIn("Icon=pydm", desktop)
            r = subprocess.run([launcher, "--help"], env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
