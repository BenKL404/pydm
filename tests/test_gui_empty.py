"""État vide de la liste : illustration, titre et sous-titre selon la situation."""
import unittest

from tests.qt import HAS_QT, app
from tests.test_gui_model import FakeTask
from tests.test_gui_window import WindowCase


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class EmptyStateTest(WindowCase):
    def test_etat_vide_situations(self):
        w = self.window()
        w.tick()
        self.assertEqual(w.empty.current, "vide")
        self.assertEqual(w.empty.title.text(), "Aucun téléchargement pour l'instant")
        self.assertEqual(w.empty.subtitle.text(),
                         "Collez un lien, glissez-le ici, ou cliquez sur ⬇ dans le navigateur")
        w.model.add(FakeTask("a.zip", status="Terminé"))
        w.search.setText("zzz")
        w.tick()
        self.assertTrue(w.empty.isVisibleTo(w))
        self.assertEqual(w.empty.current, "recherche-vide")
        self.assertEqual(w.empty.title.text(), "Aucun résultat pour « zzz »")
        w.search.clear()
        w.sidebar.state_tree.setCurrentItem(w.sidebar.state_tree.topLevelItem(5))     # En erreur
        w.tick()
        self.assertEqual(w.empty.current, "filtre-vide")
        self.assertEqual(w.empty.title.text(), "Rien ici pour l'instant")

    def test_recherche_html(self):
        from PySide6.QtCore import Qt
        w = self.window()
        w.model.add(FakeTask("a.zip"))
        w.search.setText("<b>x</b>" * 40)
        w.tick()
        self.assertEqual(w.empty.title.textFormat(), Qt.PlainText)
        self.assertLessEqual(w.minimumSizeHint().width(), 900)

    def test_zone_basse(self):
        w = self.window()
        w.show()                    # hors écran : les redimensionnements ne sont livrés qu'une fois affiché
        self.addCleanup(w.hide)
        w.tick()
        w.empty.resize(600, 150)
        self.assertTrue(w.empty.art.isHidden())
        w.empty.resize(600, 400)
        self.assertFalse(w.empty.art.isHidden())

    def test_theme_suit(self):
        from pydm.gui import theme
        w = self.window()
        w.tick()
        theme.apply(app(), "light")
        w.refresh_icons()
        light = w.empty.art.pixmap().toImage()
        theme.apply(app(), "dark")
        self.addCleanup(theme.apply, app(), "light")
        w.refresh_icons()
        self.assertNotEqual(w.empty.art.pixmap().toImage(), light)


    def test_menus_suivent_le_theme(self):
        from pydm.gui import theme
        w = self.window()
        theme.apply(app(), "light")
        self.addCleanup(theme.apply, app(), "light")
        w.refresh_icons()

        def images():
            acts = [a for a in w.schedule_menu.actions() if not a.isSeparator()]
            items = [w.sidebar.state_tree.topLevelItem(0), w.sidebar.type_tree.topLevelItem(0)]
            return ([a.icon().pixmap(24, 24).toImage() for a in acts]
                    + [i.icon(0).pixmap(24, 24).toImage() for i in items])
        light = images()
        theme.apply(app(), "dark")
        w.refresh_icons()
        for before, after in zip(light, images()):
            self.assertNotEqual(before, after)

if __name__ == "__main__":
    unittest.main()
