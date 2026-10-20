import os
import tempfile
import unittest

from tests.qt import HAS_QT, app


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class PrefsTest(unittest.TestCase):
    def setUp(self):
        app()
        from pydm import store
        from pydm.gui import prefs
        self.store, self.prefs = store, prefs

    def test_autostart(self):
        with tempfile.TemporaryDirectory() as home:
            path = os.path.join(home, ".config", "autostart", "pydm.desktop")
            self.prefs.set_autostart(True, home=home)
            with open(path) as f:
                content = f.read()
            self.assertIn(f'Exec="{home}/.local/bin/pydm" --minimized', content)
            self.assertIn("Icon=pydm", content)
            self.prefs.set_autostart(False, home=home)
            self.assertFalse(os.path.exists(path))
            self.prefs.set_autostart(False, home=home)      # déjà absent : pas d'erreur

    def test_dialogue_preferences(self):
        settings = dict(self.store.DEFAULTS)
        dlg = self.prefs.PreferencesDialog(settings, tray_available=False)
        self.assertFalse(dlg.close_to_tray_box.isEnabled())
        dlg.theme_box.setCurrentText("Sombre")
        dlg.parts_spin.setValue(4)
        result = dlg.result_settings()
        self.assertEqual(result["theme"], "dark")
        self.assertEqual(result["parts"], 4)
        self.assertEqual({k: v for k, v in result.items() if k not in ("theme", "parts")},
                         {k: v for k, v in settings.items() if k not in ("theme", "parts")})
        self.assertEqual(settings["theme"], "system")        # l'original n'est pas modifié


    def test_case_confirmation(self):
        dlg = self.prefs.PreferencesDialog(dict(self.store.DEFAULTS), tray_available=True)
        self.assertTrue(dlg.confirm_box.isChecked())
        dlg.confirm_box.setChecked(False)
        self.assertIs(dlg.result_settings()["confirm_add"], False)


    def test_rangement(self):
        dlg = self.prefs.PreferencesDialog(dict(self.store.DEFAULTS), tray_available=True)
        self.assertTrue(dlg.sort_box.isChecked())
        self.assertEqual(dlg.dir_edits["image"].text(), "Images")
        dlg.sort_box.setChecked(False)
        dlg.dir_edits["video"].setText("/media/disque/Films")
        dlg.dir_edits["music"].setText("  ")
        r = dlg.result_settings()
        self.assertIs(r["sort_by_type"], False)
        self.assertEqual(r["category_dirs"]["video"], "/media/disque/Films")
        self.assertEqual(r["category_dirs"]["music"], "Musique")      # vide → valeur par défaut


if __name__ == "__main__":
    unittest.main()
