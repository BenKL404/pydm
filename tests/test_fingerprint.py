import platform
import unittest
from unittest import mock

from pydm import fingerprint


class PlatformUATest(unittest.TestCase):
    def setUp(self):
        fingerprint.reset()
        self.addCleanup(fingerprint.reset)

    def test_trois_plateformes(self):
        for system, marker in (("Linux", "X11; Linux x86_64"), ("Windows", "Windows NT 10.0; Win64; x64"),
                               ("Darwin", "Macintosh; Intel Mac OS X")):
            with mock.patch("platform.system", return_value=system):
                self.assertEqual(fingerprint.platform_key(), system)
                self.assertIn(marker, fingerprint.default_ua())

    def test_plateforme_inconnue_repli_linux(self):
        with mock.patch("platform.system", return_value="FreeBSD"):
            self.assertEqual(fingerprint.platform_key(), "Linux")
            self.assertIn("X11; Linux x86_64", fingerprint.default_ua())

    def test_ua_du_pool_coherent_avec_la_plateforme(self):
        """Pas d'UA X11 sur un build Windows : la plateforme décide, pas un tirage au sort."""
        self.assertEqual(set(fingerprint.UA_POOL), {"Linux", "Windows", "Darwin"})
        self.assertEqual(fingerprint.default_ua(), fingerprint.UA_POOL[platform.system()]
                         if platform.system() in fingerprint.UA_POOL else fingerprint.UA_POOL["Linux"])
        self.assertNotIn("PyDM", fingerprint.default_ua())


class PinTest(unittest.TestCase):
    def setUp(self):
        fingerprint.reset()
        self.addCleanup(fingerprint.reset)

    def test_epingle_par_domaine(self):
        self.assertEqual(fingerprint.pinned_ua("https://a.fr/f", "Firefox/145.0"), "Firefox/145.0")
        self.assertEqual(fingerprint.pinned_ua("https://a.fr/autre"), "Firefox/145.0")
        self.assertEqual(fingerprint.pinned_ua("https://A.FR:443/x"), "Firefox/145.0")
        self.assertEqual(fingerprint.pinned_ua("https://b.fr/f"), fingerprint.default_ua())

    def test_le_navigateur_a_toujours_raison(self):
        fingerprint.pinned_ua("https://a.fr/f")
        self.assertEqual(fingerprint.pinned_ua("https://a.fr/f", "Chrome/142"), "Chrome/142")
        self.assertEqual(fingerprint.pinned_ua("https://a.fr/f", "Chrome/143"), "Chrome/143")
        self.assertEqual(fingerprint.pinned_ua("https://a.fr/f"), "Chrome/143")

    def test_ua_vide_ignore(self):
        self.assertEqual(fingerprint.pinned_ua("https://a.fr/f", ""), fingerprint.default_ua())
        self.assertEqual(fingerprint.pinned_ua("sans-schema"), fingerprint.default_ua())


if __name__ == "__main__":
    unittest.main()
