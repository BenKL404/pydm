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



SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
       '<rect x="0" y="0" width="10" height="32" fill="#010101"/>'
       '<rect x="11" y="0" width="10" height="32" fill="#fefefe"/>'
       '<rect x="22" y="0" width="10" height="32" fill="#ef4444"/></svg>')


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class MarkerTest(unittest.TestCase):
    """Icônes et illustrations à deux tons : corps et détail suivent le thème, l'accent reste fixe."""

    def setUp(self):
        import os
        import tempfile
        from unittest import mock
        app()
        from pydm.gui import theme
        self.theme = theme
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with open(os.path.join(tmp.name, "essai.svg"), "w") as f:
            f.write(SVG)
        for name in ("ICONS_DIR", "ILLUSTRATIONS_DIR"):
            p = mock.patch.object(theme, name, tmp.name)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(theme.apply, app(), "light")

    def colors_at(self, img, scale):
        return [img.pixelColor(int(x * scale), int(16 * scale)).name() for x in (5, 16, 27)]

    def test_icone_suit_le_theme(self):
        self.theme.apply(app(), "light")
        img = self.theme.icon("essai").pixmap(32, 32).toImage()
        self.assertEqual(self.colors_at(img, img.width() / 32), ["#334155", "#ffffff", "#ef4444"])
        self.theme.apply(app(), "dark")
        img = self.theme.icon("essai").pixmap(32, 32).toImage()
        self.assertEqual(self.colors_at(img, img.width() / 32), ["#cbd5e1", "#0f172a", "#ef4444"])

    def test_illustration_haute_densite_et_theme(self):
        self.theme.apply(app(), "light")
        pix = self.theme.illustration("essai", 100, 2.0)
        self.assertEqual(pix.devicePixelRatio(), 2.0)
        self.assertEqual(pix.width(), 200)                      # pixels physiques
        self.assertEqual(pix.height(), 200)                     # proportions du viewBox (carré)
        self.assertEqual(self.colors_at(pix.toImage(), 200 / 32), ["#334155", "#ffffff", "#ef4444"])
        self.theme.apply(app(), "dark")
        dark = self.theme.illustration("essai", 100, 2.0)
        self.assertEqual(self.colors_at(dark.toImage(), 200 / 32)[0], "#cbd5e1")

if __name__ == "__main__":
    unittest.main()
