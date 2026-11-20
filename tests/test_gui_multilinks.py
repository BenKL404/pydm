"""Ajouter plusieurs liens d'un coup : fenêtre dédiée et collage dans le champ de lien."""
import unittest
from unittest import mock

from tests.qt import HAS_QT, app
from tests.test_gui_window import WindowCase

LINKS = "https://a.fr/1.zip\nhttps://a.fr/2.zip\nhttps://a.fr/3.zip"


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class MultiLinksDialogTest(unittest.TestCase):
    def setUp(self):
        app()
        from pydm.gui.multilinks import MultiLinksDialog
        self.dlg = MultiLinksDialog()
        self.addCleanup(self.dlg.deleteLater)

    def test_compteur(self):
        d = self.dlg
        self.assertEqual(d.count_label.text(), "Aucun lien trouvé")
        self.assertFalse(d.continue_btn.isEnabled())
        d.edit.setPlainText("voir https://a.fr/1.zip")
        self.assertEqual(d.count_label.text(), "1 lien trouvé")
        d.edit.setPlainText("voir https://a.fr/1.zip et https://a.fr/2.zip\nhttps://a.fr/1.zip ftp://b.fr/x\nmerci")
        self.assertEqual(d.count_label.text(), "3 liens trouvés")              # doublon ignoré, texte mêlé
        self.assertTrue(d.continue_btn.isEnabled())
        self.assertEqual(d.urls(), ["https://a.fr/1.zip", "https://a.fr/2.zip", "ftp://b.fr/x"])


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class PasteLinksTest(WindowCase):
    def setUp(self):
        super().setUp()
        self.settings["clipboard"] = False      # la surveillance du presse-papiers remplirait le champ

    def paste(self, w, text):
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(text)
        w.link.paste()

    def test_un_lien_reste_dans_le_champ(self):
        w = self.window()
        self.paste(w, "https://a.fr/1.zip")
        self.assertEqual(w.link.text(), "https://a.fr/1.zip")
        self.assertEqual(self.factory.calls, [])

    def test_plusieurs_liens_sans_confirmation(self):
        w = self.window()
        self.paste(w, LINKS)
        self.assertEqual(w.link.text(), "")
        self.assertTrue(self.tick_until(w, lambda: len(self.factory.calls) == 3))
        self.assertEqual([c["url"] for c in self.factory.calls],
                         ["https://a.fr/1.zip", "https://a.fr/2.zip", "https://a.fr/3.zip"])

    def test_plusieurs_liens_avec_confirmation(self):
        self.settings["confirm_add"] = True
        w = self.window()
        with mock.patch.object(w, "_open_add_dialog") as dialog:
            self.paste(w, LINKS)
        self.assertEqual(dialog.call_args.args[0], ["https://a.fr/1.zip", "https://a.fr/2.zip", "https://a.fr/3.zip"])

    def test_frappe_ne_declenche_rien(self):
        w = self.window()
        w.link.setFocus()
        for ch in "https://a.fr/1.zip https://b.fr/2.zip":
            w.link.insert(ch)               # un caractère à la fois, comme au clavier
        self.assertEqual(self.factory.calls, [])
        self.assertIn("https://b.fr/2.zip", w.link.text())

    def test_champ_rempli_par_le_programme(self):
        w = self.window()
        w.link.setText("https://a.fr/1.zip https://a.fr/2.zip")      # surveillance du presse-papiers, par ex.
        w.link.setCursorPosition(len(w.link.text()))
        w.link.insert("x")                                             # puis une seule touche
        self.assertEqual(self.factory.calls, [])
        self.assertTrue(w.link.text().endswith("x"))

    def test_entree_du_menu(self):
        w = self.window()
        texts = [a.text() for a in w.menu.actions()]
        self.assertIn("Ajouter plusieurs liens…\tCtrl+Maj+V", texts)
        with mock.patch("pydm.gui.window.MultiLinksDialog") as dlg:
            dlg.return_value.exec.return_value = 1
            dlg.return_value.urls.return_value = ["https://a.fr/1.zip", "https://a.fr/2.zip"]
            w.open_multi_links()
        self.assertTrue(self.tick_until(w, lambda: len(self.factory.calls) == 2))


if __name__ == "__main__":
    unittest.main()
