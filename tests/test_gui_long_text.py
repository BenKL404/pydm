"""Textes très longs (titres, URL sans espace) : aucune fenêtre ne doit s'élargir au-delà de l'écran."""
import os
import tempfile
import time
import unittest
from unittest import mock

from tests.qt import HAS_QT, app

URL = ("https://cdn.exemple.fr/hls2/08/00064/,j5in87x8ckil_n,.urlset/index-a1.m3u8?t="
       + "ajzrrU3y00akrAcAnZ6BUdfbPe3vzfYJKijpYzus" * 4)
TITLE = ("Un titre de vidéo vraiment très très long " * 8).strip()
MAX_WIDTH = 900         # bien en dessous d'un écran de portable (1366 px)


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class LongTextTest(unittest.TestCase):
    def setUp(self):
        app()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = tmp.name
        for name, value in (("CONFIG_DIR", self.cfg), ("SOCKET_PATH", os.path.join(self.cfg, "s"))):
            p = mock.patch(f"pydm.ipc.{name}", value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch("pydm.gui.adddialog.fetch_youtube_thumbnail", return_value=None)
        p.start()
        self.addCleanup(p.stop)
        from pydm import store
        self.settings = dict(store.DEFAULTS, folder=self.cfg, confirm_add=False, show_progress=False)

    def task(self):
        from tests.test_gui_window import FakeDownload
        t = FakeDownload(URL, self.cfg)
        t.name = "x" * 200 + ".mp4"
        return t

    def test_coupure_invisible(self):
        from pydm.gui.widgets import breakable
        self.assertEqual(breakable("un texte court normal"), "un texte court normal")
        long = "a" * 100
        self.assertIn("​", breakable(long))
        self.assertEqual(breakable(long).replace("​", ""), long)
        self.assertEqual(breakable(URL).replace("​", ""), URL)

    def test_fenetre_principale(self):
        from pydm.gui.window import MainWindow
        from tests.test_gui_window import Factory
        w = MainWindow(self.settings, factory=Factory())
        self.addCleanup(w.deleteLater)
        t = self.task()
        w.model.add(t)
        w.detail.show_task(t)
        self.assertLessEqual(w.minimumSizeHint().width(), MAX_WIDTH)

    def test_fenetre_de_progression(self):
        from pydm.gui.progress import ProgressDialog
        from pydm.gui.window import MainWindow
        from tests.test_gui_window import Factory
        w = MainWindow(self.settings, factory=Factory())
        self.addCleanup(w.deleteLater)
        d = ProgressDialog(self.task(), w)
        self.addCleanup(d.deleteLater)
        self.assertLessEqual(d.minimumSizeHint().width(), MAX_WIDTH)

    def dialog(self, res, title=None):
        from pydm.gui.adddialog import AddDialog
        d = AddDialog(self.settings, [URL], analyzer=lambda *a, **k: res, title=title)
        self.addCleanup(d.deleteLater)
        d.show()
        end = time.time() + 2
        while d.done_count() < 1 and time.time() < end:
            d.poll()
            time.sleep(0.02)
        return d

    def test_fenetre_d_ajout_url_sans_titre(self):
        from tests.test_gui_adddialog import result
        d = self.dialog(result(kind="error", error="x", title=None, name=None, choices=[]))
        self.assertLessEqual(d.minimumSizeHint().width(), MAX_WIDTH)
        self.assertLessEqual(d.sizeHint().width(), MAX_WIDTH)

    def test_titre_long_sur_deux_lignes(self):
        from tests.test_gui_adddialog import result
        d = self.dialog(result(title=TITLE, name=TITLE + ".mp4"), title=TITLE)
        self.assertLessEqual(d.sizeHint().width(), MAX_WIDTH)
        label = d.title_label
        lines = label.fontMetrics().lineSpacing()
        self.assertLessEqual(label.heightForWidth(400), 2 * lines + 4)       # deux lignes au plus
        self.assertEqual(label.toolTip(), TITLE)                              # titre complet au survol
        self.assertEqual(label.full_text(), TITLE)


    def test_emoji(self):
        from pydm.gui.widgets import ElidedLabel
        text = "😀😀😀 Titre avec émojis 🎵🎶 " * 6
        full = ElidedLabel(text, max_lines=50)
        lines = full._lines(300)
        self.assertEqual(" ".join(lines).split(), text.split())      # coupures entre les mots, rien de perdu
        self.assertTrue(all(lines))
        two = ElidedLabel(text, max_lines=2)._lines(300)
        self.assertEqual(len(two), 2)
        self.assertTrue(text.startswith(two[0]))
        self.assertTrue(two[1].endswith("…"))

    def test_titre_avec_balises(self):
        from PySide6.QtCore import Qt
        from pydm.gui.widgets import ElidedLabel
        label = ElidedLabel("Comment utiliser <b>gras</b> et <br> en HTML", max_lines=2)
        self.assertEqual(label.textFormat(), Qt.PlainText)
        self.assertIn("<b>", label.text())

    def test_texte_selectionnable_sans_coupures(self):
        from PySide6.QtCore import Qt
        from pydm.gui.progress import ProgressDialog
        from pydm.gui.widgets import DetailPanel
        panel = DetailPanel()
        self.addCleanup(panel.deleteLater)
        self.assertFalse(panel.label.textInteractionFlags() & Qt.TextSelectableByMouse)  # liens seulement
        self.assertTrue(panel.label.textInteractionFlags() & Qt.LinksAccessibleByMouse)
        from pydm.gui.window import MainWindow
        from tests.test_gui_window import Factory
        w = MainWindow(self.settings, factory=Factory())
        self.addCleanup(w.deleteLater)
        d = ProgressDialog(self.task(), w)
        self.addCleanup(d.deleteLater)
        self.assertFalse(d.values["Statut"].textInteractionFlags() & Qt.TextSelectableByMouse)

if __name__ == "__main__":
    unittest.main()
