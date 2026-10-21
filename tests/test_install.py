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
@unittest.skipIf(os.name == "nt", "install.sh (Linux)")
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


    def install(self, home, **extra):
        env = dict(os.environ, HOME=home, **extra)
        env.pop("PYDM_CONFIG_DIR", None)
        return subprocess.run(["sh", os.path.join(ROOT, "install.sh")], env=env, capture_output=True,
                              text=True, timeout=300), env

    def test_hors_ligne_avec_pyside6_deja_la(self):
        with tempfile.TemporaryDirectory() as home:
            r, _ = self.install(home, PYDM_SKIP_PIP="1")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            py = os.path.join(home, ".local/share/pydm/venv/bin/python")
            site = subprocess.run([py, "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                                  capture_output=True, text=True).stdout.strip()
            os.makedirs(os.path.join(site, "PySide6"))
            open(os.path.join(site, "PySide6", "__init__.py"), "w").close()
            r, _ = self.install(home, PIP_INDEX_URL="http://127.0.0.1:9/simple", PIP_RETRIES="0",
                                PIP_TIMEOUT="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("hors ligne", r.stdout)

    def test_dossier_personnel_avec_caracteres_speciaux(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = os.path.join(tmp, 'mon "dossier" $HOME')
            os.makedirs(home)
            r, env = self.install(home, PYDM_SKIP_PIP="1")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            launcher = os.path.join(home, ".local/bin/pydm")
            r = subprocess.run([launcher, "--help"], env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(os.path.join(home, ".mozilla/native-messaging-hosts/com.pydm.host.json")) as f:
                self.assertEqual(json.load(f)["path"], os.path.join(home, ".local/share/pydm/pydm_host.py"))


if __name__ == "__main__":
    unittest.main()
