import unittest

from tests.qt import HAS_QT, app

NAMES = ("add", "resume", "pause", "force", "remove", "folder", "search", "schedule", "menu",
         "type-video", "type-music", "type-document", "type-image", "type-archive", "type-program", "type-other")


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class ThemeTest(unittest.TestCase):
    def setUp(self):
        app()
        from pydm.gui import theme
        self.theme = theme

    def test_toutes_les_icones(self):
        for name in NAMES:
            with self.subTest(name=name):
                icon = self.theme.icon(name)
                self.assertFalse(icon.isNull())
                self.assertFalse(icon.pixmap(24, 24).isNull())

    def test_recoloration(self):
        img = self.theme.icon("pause", "#ff0000").pixmap(24, 24).toImage()
        k = img.width() / 24        # échelle de l'écran (HiDPI)
        glyph = img.pixelColor(int(4 * k), int(12 * k))
        self.assertGreater(glyph.red(), 200)
        self.assertLess(glyph.green(), 50)
        self.assertEqual(img.pixelColor(int(10 * k), int(12 * k)).alpha(), 0)    # découpe de la barre gauche

    def test_logo(self):
        self.assertFalse(self.theme.logo().isNull())

    def test_theme_sombre(self):
        self.theme.apply(app(), "dark")
        self.assertTrue(self.theme.is_dark())
        self.theme.apply(app(), "light")
        self.assertFalse(self.theme.is_dark())


if __name__ == "__main__":
    unittest.main()
