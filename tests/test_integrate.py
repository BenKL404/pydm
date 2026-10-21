import json
import os
import shlex
import subprocess
import tempfile
import unittest
from unittest import mock

from pydm import integrate

CHROME_ID = "feloklndigmnjlmffbddgcdfigpnbcba"


@unittest.skipIf(os.name == "nt", "intégration de l'AppImage (Linux)")
class IntegrateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)
        apps = os.path.join(self.tmp.name, "Mes apps")
        os.makedirs(apps)
        self.appimage = os.path.join(apps, 'Py"DM $1.AppImage')
        open(self.appimage, "w").close()

    def tearDown(self):
        for root, dirs, _ in os.walk(self.tmp.name):
            for d in dirs:
                os.chmod(os.path.join(root, d), 0o755)
        self.tmp.cleanup()

    def path(self, *parts):
        return os.path.join(self.home, *parts)

    def wrapper(self):
        return self.path(".local", "share", "pydm", "pydm-host")

    def manifest(self, folder):
        with open(self.path(folder, "com.pydm.host.json")) as f:
            return json.load(f)

    def read(self, *parts):
        with open(self.path(*parts)) as f:
            return f.read()

    def test_premiere_integration(self):
        self.assertEqual(integrate.integrate(self.appimage, home=self.home), "new")
        wrapper = self.wrapper()
        self.assertTrue(os.stat(wrapper).st_mode & 0o111)
        self.assertEqual(subprocess.run(["sh", "-n", wrapper]).returncode, 0)
        with open(wrapper) as f:
            self.assertEqual(f.read().strip().splitlines()[-1],
                             f'exec {shlex.quote(self.appimage)} --native-host "$@"')
        firefox = self.manifest(".mozilla/native-messaging-hosts")
        self.assertEqual(firefox["path"], wrapper)
        self.assertEqual(firefox["allowed_extensions"], ["pydm@local"])
        self.assertEqual(firefox["name"], "com.pydm.host")
        chrome = self.manifest(".config/google-chrome/NativeMessagingHosts")
        self.assertEqual(chrome["allowed_origins"], [f"chrome-extension://{CHROME_ID}/"])
        desktop = self.read(".local", "share", "applications", "pydm.desktop")
        self.assertIn("Exec=" + integrate.desktop_quote(self.appimage) + "\n", desktop)
        self.assertIn("Icon=pydm", desktop)
        self.assertTrue(os.path.exists(self.path(".local/share/icons/hicolor/48x48/apps/pydm.png")))

    def test_navigateurs_presents_seulement(self):
        os.makedirs(self.path(".config", "BraveSoftware", "Brave-Browser"))
        integrate.integrate(self.appimage, home=self.home)
        self.assertTrue(os.path.exists(self.path(".config/BraveSoftware/Brave-Browser/NativeMessagingHosts",
                                                 "com.pydm.host.json")))
        self.assertFalse(os.path.exists(self.path(".config", "vivaldi")))

    def test_rien_a_refaire(self):
        integrate.integrate(self.appimage, home=self.home)
        before = os.stat(self.wrapper()).st_mtime_ns
        self.assertEqual(integrate.integrate(self.appimage, home=self.home), "same")
        self.assertEqual(os.stat(self.wrapper()).st_mtime_ns, before)

    def test_appimage_deplacee(self):
        integrate.integrate(self.appimage, home=self.home)
        moved = os.path.join(self.tmp.name, "PyDM.AppImage")
        os.rename(self.appimage, moved)
        self.assertEqual(integrate.integrate(moved, home=self.home), "updated")
        self.assertIn(shlex.quote(moved), self.read(".local", "share", "pydm", "pydm-host"))
        self.assertIn(integrate.desktop_quote(moved), self.read(".local", "share", "applications", "pydm.desktop"))

    def test_manifeste_supprime_recree(self):
        integrate.integrate(self.appimage, home=self.home)
        os.remove(self.path(".mozilla/native-messaging-hosts/com.pydm.host.json"))
        self.assertEqual(integrate.integrate(self.appimage, home=self.home), "same")
        self.assertEqual(self.manifest(".mozilla/native-messaging-hosts")["path"], self.wrapper())

    def test_remove_epargne_install_sh(self):
        os.makedirs(self.path(".config", "pydm"))
        with open(self.path(".config", "pydm", "settings.json"), "w") as f:
            f.write("{}")
        integrate.integrate(self.appimage, home=self.home)
        brave = self.path(".config/BraveSoftware/Brave-Browser/NativeMessagingHosts")
        os.makedirs(brave)
        with open(os.path.join(brave, "com.pydm.host.json"), "w") as f:     # installation install.sh
            json.dump({"name": "com.pydm.host", "path": self.path(".local/share/pydm/pydm_host.py")}, f)
        integrate.remove(home=self.home)
        self.assertFalse(os.path.exists(self.wrapper()))
        self.assertFalse(os.path.exists(self.path(".mozilla/native-messaging-hosts/com.pydm.host.json")))
        self.assertFalse(os.path.exists(self.path(".local/share/applications/pydm.desktop")))
        self.assertFalse(os.path.exists(self.path(".local/share/icons/hicolor/48x48/apps/pydm.png")))
        self.assertTrue(os.path.exists(os.path.join(brave, "com.pydm.host.json")))
        self.assertTrue(os.path.exists(self.path(".config", "pydm", "settings.json")))
        integrate.remove(home=self.home)        # déjà retiré : pas d'erreur

    @unittest.skipIf(getattr(os, "geteuid", lambda: -1)() == 0, "root ignore les droits")
    def test_lecture_seule(self):
        os.makedirs(self.path(".local"))
        os.chmod(self.path(".local"), 0o500)
        with self.assertRaises(OSError):
            integrate.integrate(self.appimage, home=self.home)

    def test_appimage_path(self):
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop("APPIMAGE", None)
            self.assertIsNone(integrate.appimage_path())
            os.environ["APPIMAGE"] = os.path.join(self.tmp.name, "absent.AppImage")
            self.assertIsNone(integrate.appimage_path())
            os.environ["APPIMAGE"] = self.appimage
            self.assertEqual(integrate.appimage_path(), self.appimage)

    def test_launcher(self):
        with mock.patch.object(integrate, "appimage_path", return_value=None):
            self.assertEqual(integrate.launcher(home=self.home), self.path(".local", "bin", "pydm"))
        with mock.patch.object(integrate, "appimage_path", return_value=self.appimage):
            self.assertEqual(integrate.launcher(home=self.home), self.appimage)

    def test_desktop_quote(self):
        self.assertEqual(integrate.desktop_quote("/a b/x"), '"/a b/x"')
        self.assertEqual(integrate.desktop_quote('/a"$`\\'), '"/a\\\\"\\\\$\\\\`\\\\\\\\"')


    def autostart(self):
        return self.path(".config", "autostart", "pydm.desktop")

    def test_autostart_suit_appimage_deplacee(self):
        integrate.integrate(self.appimage, home=self.home)
        integrate.set_autostart(True, home=self.home, launcher=self.appimage)
        moved = os.path.join(self.tmp.name, "PyDM-1.4.0.AppImage")
        os.rename(self.appimage, moved)
        integrate.integrate(moved, home=self.home)
        with open(self.autostart()) as f:
            self.assertIn("Exec=" + integrate.desktop_quote(moved) + " --minimized", f.read())

    def test_autostart_absent_pas_cree(self):
        integrate.integrate(self.appimage, home=self.home)
        self.assertFalse(os.path.exists(self.autostart()))

    def test_remove_retire_autostart(self):
        integrate.integrate(self.appimage, home=self.home)
        integrate.set_autostart(True, home=self.home, launcher=self.appimage)
        integrate.remove(home=self.home)
        self.assertFalse(os.path.exists(self.autostart()))
        integrate.set_autostart(True, home=self.home, launcher=self.path(".local", "bin", "pydm"))   # install.sh
        integrate.remove(home=self.home)
        self.assertTrue(os.path.exists(self.autostart()))

    def test_derniere_installation_gagne(self):
        integrate.integrate(self.appimage, home=self.home)
        firefox = self.path(".mozilla/native-messaging-hosts/com.pydm.host.json")
        with open(firefox, "w") as f:                                        # install.sh relancé ensuite
            json.dump({"name": "com.pydm.host", "path": self.path(".local/share/pydm/pydm_host.py")}, f)
        with open(self.path(".local/share/applications/pydm.desktop"), "w") as f:
            f.write('[Desktop Entry]\nExec="' + self.path(".local/bin/pydm") + '"\n')
        self.assertEqual(integrate.integrate(self.appimage, home=self.home), "same")
        self.assertEqual(self.manifest(".mozilla/native-messaging-hosts")["path"], self.wrapper())
        self.assertIn(integrate.desktop_quote(self.appimage), self.read(".local/share/applications/pydm.desktop"))

    def test_mode_extraction_sans_fuse(self):
        with mock.patch.dict(os.environ, {"APPIMAGE_EXTRACT_AND_RUN": "1"}):
            integrate.integrate(self.appimage, home=self.home)
            integrate.set_autostart(True, home=self.home, launcher=self.appimage)
        with open(self.wrapper()) as f:
            self.assertEqual(f.read().strip().splitlines()[-1],
                             f'APPIMAGE_EXTRACT_AND_RUN=1 exec {shlex.quote(self.appimage)} --native-host "$@"')
        exec_line = "Exec=env APPIMAGE_EXTRACT_AND_RUN=1 " + integrate.desktop_quote(self.appimage)
        self.assertIn(exec_line + "\n", self.read(".local/share/applications/pydm.desktop"))
        with open(self.autostart()) as f:
            self.assertIn(exec_line + " --minimized", f.read())

    def test_installed_app_windows(self):
        exe = "C:\\Programs\\PyDM\\pydm.exe"
        with mock.patch.object(integrate, "WINDOWS", True), mock.patch.object(integrate.sys, "frozen", True, create=True), \
                mock.patch.object(integrate.sys, "executable", exe):
            self.assertEqual(integrate.installed_app(), exe)
        with mock.patch.object(integrate, "WINDOWS", True):
            self.assertIsNone(integrate.installed_app())            # pas figé (sources) : rien à intégrer
        with mock.patch.object(integrate, "appimage_path", return_value=self.appimage):
            self.assertEqual(integrate.installed_app(), self.appimage)

    def test_dispatch_windows(self):
        with mock.patch.object(integrate, "WINDOWS", True), \
                mock.patch.dict(os.environ, {"LOCALAPPDATA": "C:\\L"}), \
                mock.patch.object(integrate, "installed_app", return_value="C:\\P\\pydm.exe"), \
                mock.patch("pydm.integrate_win.integrate", return_value="new") as integ, \
                mock.patch("pydm.integrate_win.remove") as remove, \
                mock.patch("pydm.integrate_win.set_autostart") as autostart:
            self.assertEqual(integrate.integrate("C:\\P\\pydm.exe"), "new")
            integrate.remove()
            integrate.set_autostart(True)
        integ.assert_called_once_with("C:\\P\\pydm.exe", "C:\\L")
        remove.assert_called_once_with("C:\\L", "C:\\P\\pydm.exe")
        autostart.assert_called_once_with(True, "C:\\P\\pydm.exe")

if __name__ == "__main__":
    unittest.main()
