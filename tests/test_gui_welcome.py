import unittest
from unittest import mock

from tests.qt import HAS_QT, app


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class WelcomeTest(unittest.TestCase):
    def setUp(self):
        app()
        from PySide6.QtWidgets import QMainWindow
        from pydm.gui import app as gui_app
        from pydm.gui import welcome
        self.gui_app, self.welcome = gui_app, welcome
        self.window = QMainWindow()

    def tearDown(self):
        dlg = getattr(self.window, "welcome", None)
        if dlg:
            dlg.close()
        self.window.close()

    def run_integration(self, status=None, error=None):
        with mock.patch("pydm.integrate.appimage_path", return_value="/x/PyDM.AppImage"), \
                mock.patch("pydm.integrate.integrate", return_value=status, side_effect=error) as integ:
            return self.gui_app.integrate_system(self.window), integ

    def test_hors_appimage(self):
        with mock.patch("pydm.integrate.appimage_path", return_value=None), \
                mock.patch("pydm.integrate.integrate") as integ:
            self.assertIsNone(self.gui_app.integrate_system(self.window))
        integ.assert_not_called()
        self.assertIsNone(getattr(self.window, "welcome", None))

    def test_message_premiere_fois(self):
        status, integ = self.run_integration("new")
        self.assertEqual(status, "new")
        integ.assert_called_once_with("/x/PyDM.AppImage")
        self.assertIsInstance(self.window.welcome, self.welcome.WelcomeDialog)
        self.assertTrue(self.window.welcome.isVisible())
        self.assertIn("PyDM est installé", self.window.welcome.text())

    def test_pas_de_message_ensuite(self):
        for status in ("updated", "same"):
            self.assertEqual(self.run_integration(status)[0], status)
            self.assertIsNone(getattr(self.window, "welcome", None))

    def test_echec_non_bloquant(self):
        status, _ = self.run_integration(error=PermissionError("lecture seule"))
        self.assertIsNone(status)
        self.assertTrue(self.window.statusBar().currentMessage().startswith("Intégration au système impossible"))

    def test_boutons_liens(self):
        from PySide6.QtCore import QUrl
        dlg = self.welcome.WelcomeDialog()
        with mock.patch("pydm.gui.welcome.QDesktopServices.openUrl") as open_url:
            dlg.firefox_btn.click()
            dlg.chrome_btn.click()
        self.assertEqual([c.args[0] for c in open_url.call_args_list],
                         [QUrl(self.welcome.RELEASES_URL), QUrl(self.welcome.CHROME_URL)])


if __name__ == "__main__":
    unittest.main()
