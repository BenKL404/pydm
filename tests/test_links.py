import unittest

from pydm.gui.links import extract_urls


class ExtractUrlsTest(unittest.TestCase):
    def test_multiligne_et_doublons(self):
        text = "https://a.fr/x.zip\nhttps://a.fr/x.zip  http://b.fr/y"
        self.assertEqual(extract_urls(text), ["https://a.fr/x.zip", "http://b.fr/y"])

    def test_uri_list(self):
        self.assertEqual(extract_urls("# commentaire\r\nhttps://a.fr/1\r\nhttps://a.fr/2\r\n"),
                         ["https://a.fr/1", "https://a.fr/2"])

    def test_schemas_refuses(self):
        text = "javascript:alert(1) file:///etc/passwd ftp://f.fr/a mailto:x@y.fr"
        self.assertEqual(extract_urls(text), ["ftp://f.fr/a"])

    def test_ponctuation_et_unicode(self):
        self.assertEqual(extract_urls("Voir (https://exemple.fr/été%202026.mp4)."),
                         ["https://exemple.fr/été%202026.mp4"])


if __name__ == "__main__":
    unittest.main()
