import os
import tempfile
import unittest
from unittest import mock

from tests.qt import HAS_QT, app
from tests.test_gui_model import FakeTask


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class SidebarTest(unittest.TestCase):
    def setUp(self):
        app()
        from pydm.gui.sidebar import Sidebar
        self.bar = Sidebar()
        self.addCleanup(self.bar.deleteLater)

    def labels(self, tree):
        return [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]

    def test_entrees(self):
        self.assertEqual(self.labels(self.bar.state_tree),
                         ["Tous", "En cours", "En file", "En pause", "Terminés", "En erreur"])
        self.assertEqual(self.labels(self.bar.type_tree),
                         ["Tous", "Vidéos", "Musique", "Documents", "Images", "Archives", "Programmes", "Autres"])
        self.assertEqual((self.bar.state_key(), self.bar.type_key()), ("all", "all"))

    def test_compteurs(self):
        from pydm.gui.model import counts
        states, types = counts([FakeTask("a.mkv", status="Terminé"), FakeTask("b.zip")])
        self.bar.update_counts(states, types)
        self.assertEqual(self.bar.state_tree.topLevelItem(4).text(1), "1")     # Terminés
        self.assertEqual(self.bar.type_tree.topLevelItem(1).text(1), "1")      # Vidéos
        self.assertEqual(self.bar.type_tree.topLevelItem(2).text(1), "0")      # Musique

    def test_selection_emet_le_filtre(self):
        got = []
        self.bar.filter_changed.connect(lambda s, t: got.append((s, t)))
        self.bar.state_tree.setCurrentItem(self.bar.state_tree.topLevelItem(4))
        self.bar.type_tree.setCurrentItem(self.bar.type_tree.topLevelItem(1))
        self.assertEqual(got[-1], ("done", "video"))


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class SidebarWindowTest(unittest.TestCase):
    def setUp(self):
        app()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = tmp.name
        for name, value in (("CONFIG_DIR", self.cfg), ("SOCKET_PATH", os.path.join(self.cfg, "s"))):
            p = mock.patch(f"pydm.ipc.{name}", value)
            p.start()
            self.addCleanup(p.stop)
        from pydm import store
        from pydm.gui.window import MainWindow
        self.store = store
        self.settings = dict(store.DEFAULTS, folder=self.cfg, confirm_add=False)
        self.w = MainWindow(self.settings)
        self.addCleanup(self.w.deleteLater)
        for name, status in (("a.mkv", "Terminé"), ("b.zip", "Terminé"), ("c.pdf", "En pause")):
            self.w.model.add(FakeTask(name, status=status))
        self.w.tick()

    def test_filtre_par_la_barre(self):
        bar = self.w.sidebar
        bar.state_tree.setCurrentItem(bar.state_tree.topLevelItem(4))     # Terminés
        self.assertEqual(self.w.proxy.rowCount(), 2)
        bar.type_tree.setCurrentItem(bar.type_tree.topLevelItem(1))       # Vidéos
        self.assertEqual(self.w.proxy.rowCount(), 1)

    def test_vue_vide(self):
        bar = self.w.sidebar
        bar.type_tree.setCurrentItem(bar.type_tree.topLevelItem(4))       # Images
        self.w.tick()
        self.assertTrue(self.w.empty.isVisibleTo(self.w))
        self.assertEqual(self.w.empty.text(), "Aucun téléchargement dans cette vue")

    def test_compteurs_a_jour(self):
        self.assertEqual(self.w.sidebar.state_tree.topLevelItem(0).text(1), "3")

    def test_masquer_ctrl_b(self):
        self.assertFalse(self.w.sidebar.isHidden())
        self.w.toggle_sidebar()
        self.assertTrue(self.w.sidebar.isHidden())
        self.assertIs(self.store.load_settings(self.cfg)["sidebar"], False)

    def test_ouvrir_dossier_de_categorie(self):
        with mock.patch("pydm.gui.window.QDesktopServices.openUrl") as open_url:
            self.w.open_category_folder("image")
        target = os.path.join(self.cfg, "Images")
        self.assertTrue(os.path.isdir(target))
        self.assertEqual(os.path.normpath(open_url.call_args.args[0].toLocalFile()), target)


if __name__ == "__main__":
    unittest.main()
