import unittest

from pydm.filetypes import category


class CategoryTest(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(category("Film.MKV"), "video")
        self.assertEqual(category("album.flac"), "music")
        self.assertEqual(category("x.tar.xz"), "archive")
        self.assertEqual(category("setup.AppImage"), "program")
        self.assertEqual(category("README"), "other")
        self.assertEqual(category(None), "other")
        self.assertEqual(category("rapport.pdf"), "document")

    def test_images(self):
        for name in ("photo.JPG", "logo.png", "anim.gif", "img.webp", "icone.svg", "IMG_0001.HEIC"):
            self.assertEqual(category(name), "image", name)


if __name__ == "__main__":
    unittest.main()
