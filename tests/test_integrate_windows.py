import json
import os
import shutil
import tempfile
import unittest

from pydm import integrate_win
from tests.fakereg import FakeReg

CHROME_ID = "feloklndigmnjlmffbddgcdfigpnbcba"
KEYS = {"Software\\Mozilla\\NativeMessagingHosts\\com.pydm.host": "firefox.json",
        "Software\\Google\\Chrome\\NativeMessagingHosts\\com.pydm.host": "chrome.json",
        "Software\\Chromium\\NativeMessagingHosts\\com.pydm.host": "chrome.json",
        "Software\\Microsoft\\Edge\\NativeMessagingHosts\\com.pydm.host": "chrome.json"}
RUN = "Software\\Microsoft\\Windows\\CurrentVersion\\Run"


class WindowsIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.local = os.path.join(self.tmp, "Local")
        self.exe = "C:\\Users\\Élodie Durand\\AppData\\Local\\Programs\\PyDM\\pydm.exe"
        self.host = "C:\\Users\\Élodie Durand\\AppData\\Local\\Programs\\PyDM\\pydm-host.exe"
        self.reg = FakeReg()

    def integrate(self, exe=None):
        return integrate_win.integrate(exe or self.exe, self.local, reg=self.reg)

    def hosts(self, name):
        return os.path.join(self.local, "PyDM", "hosts", name)

    def manifest(self, name):
        with open(self.hosts(name), encoding="utf-8") as f:
            return json.load(f)

    def run_value(self):
        return self.reg.keys.get(f"hkcu\\{RUN}".lower(), {}).get("PyDM")

    def test_premiere_integration(self):
        self.assertEqual(self.integrate(), "new")
        firefox, chrome = self.manifest("firefox.json"), self.manifest("chrome.json")
        self.assertEqual(firefox["path"], self.host)
        self.assertEqual(firefox["allowed_extensions"], ["pydm@local"])
        self.assertEqual(firefox["name"], "com.pydm.host")
        self.assertEqual(chrome["allowed_origins"], [f"chrome-extension://{CHROME_ID}/"])
        for key, name in KEYS.items():
            self.assertEqual(self.reg.value(key), self.hosts(name))

    def test_rien_a_refaire_puis_deplace(self):
        self.integrate()
        self.assertEqual(self.integrate(), "same")
        moved = "D:\\Apps\\PyDM\\pydm.exe"
        self.assertEqual(self.integrate(moved), "updated")
        self.assertEqual(self.manifest("chrome.json")["path"], "D:\\Apps\\PyDM\\pydm-host.exe")

    def test_derniere_installation_gagne(self):
        self.integrate()
        self.reg.SetValue(self.reg.HKEY_CURRENT_USER, "Software\\Microsoft\\Edge\\NativeMessagingHosts\\com.pydm.host",
                          self.reg.REG_SZ, "C:\\ailleurs\\chrome.json")
        self.assertEqual(self.integrate(), "same")
        self.assertEqual(self.reg.value("Software\\Microsoft\\Edge\\NativeMessagingHosts\\com.pydm.host"),
                         self.hosts("chrome.json"))

    def test_demarrage_avec_la_session(self):
        integrate_win.set_autostart(True, self.exe, reg=self.reg)
        self.assertEqual(self.run_value(), f'"{self.exe}" --minimized')
        integrate_win.set_autostart(False, self.exe, reg=self.reg)
        self.assertIsNone(self.run_value())
        integrate_win.set_autostart(False, self.exe, reg=self.reg)       # déjà absent : pas d'erreur

    def test_autostart_suit_le_deplacement(self):
        self.integrate()
        integrate_win.set_autostart(True, self.exe, reg=self.reg)
        self.integrate("D:\\Apps\\PyDM\\pydm.exe")
        self.assertEqual(self.run_value(), '"D:\\Apps\\PyDM\\pydm.exe" --minimized')

    def test_retrait(self):
        settings = os.path.join(self.tmp, "Roaming", "PyDM", "settings.json")
        os.makedirs(os.path.dirname(settings))
        open(settings, "w").close()
        self.integrate()
        integrate_win.set_autostart(True, self.exe, reg=self.reg)
        other = "Software\\Chromium\\NativeMessagingHosts\\com.pydm.host"      # une autre installation
        self.reg.SetValue(self.reg.HKEY_CURRENT_USER, other, self.reg.REG_SZ, "C:\\autre\\chrome.json")
        integrate_win.remove(self.local, self.exe, reg=self.reg)
        for key in KEYS:
            if key != other:
                self.assertIsNone(self.reg.value(key))
        self.assertEqual(self.reg.value(other), "C:\\autre\\chrome.json")
        self.assertIsNone(self.run_value())
        self.assertFalse(os.path.exists(os.path.join(self.local, "PyDM", "hosts")))
        self.assertTrue(os.path.exists(settings))
        integrate_win.remove(self.local, self.exe, reg=self.reg)          # déjà retiré : pas d'erreur


@unittest.skipUnless(os.name == "nt", "registre réel (Windows)")
class RealRegistryTest(unittest.TestCase):
    ROOT = "Software\\PyDM-tests"

    def setUp(self):
        import winreg
        self.winreg = winreg
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.addCleanup(self._clean)

    def _clean(self):
        def delete(path):
            try:
                with self.winreg.OpenKey(self.winreg.HKEY_CURRENT_USER, path) as k:
                    while True:
                        try:
                            delete(path + "\\" + self.winreg.EnumKey(k, 0))
                        except OSError:
                            break
                self.winreg.DeleteKey(self.winreg.HKEY_CURRENT_USER, path)
            except FileNotFoundError:
                pass
        delete(self.ROOT)

    def test_cycle(self):
        exe = os.path.join(self.tmp, "Élodie Durand", "pydm.exe")
        self.assertEqual(integrate_win.integrate(exe, self.tmp, root=self.ROOT), "new")
        self.assertEqual(integrate_win.integrate(exe, self.tmp, root=self.ROOT), "same")
        key = self.ROOT + "\\Mozilla\\NativeMessagingHosts\\com.pydm.host"
        self.assertEqual(self.winreg.QueryValue(self.winreg.HKEY_CURRENT_USER, key),
                         os.path.join(self.tmp, "PyDM", "hosts", "firefox.json"))
        integrate_win.set_autostart(True, exe, root=self.ROOT)
        integrate_win.remove(self.tmp, exe, root=self.ROOT)
        with self.assertRaises(FileNotFoundError):
            self.winreg.QueryValue(self.winreg.HKEY_CURRENT_USER, key)


if __name__ == "__main__":
    unittest.main()
