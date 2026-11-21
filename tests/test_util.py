import unittest

import os
import tempfile
from unittest import mock

from pydm.util import expand_path, safe_filename, unique_path

W = dict(windows=True)


class SafeFilenameTest(unittest.TestCase):
    def test_windows(self):
        self.assertEqual(safe_filename('Film: la suite? "VF" <1/2>|*.mp4', **W), "Film_ la suite_ _VF_ _1_2___.mp4")
        self.assertEqual(safe_filename("con.txt", **W), "_con.txt")
        self.assertEqual(safe_filename("COM1", **W), "_COM1")
        self.assertEqual(safe_filename("lpt9.tar.gz", **W), "_lpt9.tar.gz")
        self.assertEqual(safe_filename("console.txt", **W), "console.txt")
        self.assertEqual(safe_filename("fin. . ", **W), "fin")
        self.assertEqual(safe_filename("a\x01b\tc", **W), "a_b_c")
        self.assertEqual(safe_filename(" ... ", **W), "telechargement")
        self.assertEqual(safe_filename("", fallback="video", **W), "video")
        self.assertEqual(safe_filename("vidéo 🎬 東京", **W), "vidéo 🎬 東京")

    def test_linux_inchange(self):
        self.assertEqual(safe_filename('Film: la suite? <1/2>', windows=False), "Film: la suite? <1_2>")
        self.assertEqual(safe_filename("  ", windows=False), "telechargement")
        self.assertEqual(safe_filename("con.txt", windows=False), "con.txt")

    def test_tronque_puis_nettoye(self):
        name = safe_filename("é" * 80 + ". ", **W)
        self.assertEqual(name, "é" * 80)



class ExpandPathTest(unittest.TestCase):
    def test_tilde_et_separateurs(self):
        with mock.patch.dict(os.environ, {"HOME": "/h", "USERPROFILE": "/h"}):
            self.assertEqual(expand_path("~/a/../b//c"), os.path.join(os.path.normpath("/h"), "b", "c"))
        self.assertEqual(expand_path("/srv/dl/"), os.path.normpath("/srv/dl"))


if __name__ == "__main__":
    unittest.main()


class NumerotationTest(unittest.TestCase):
    """Un nom déjà numéroté repart de sa racine : « (3) » donne « (4) », jamais « (3) (1) »."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name

    def pose(self, *noms):
        for n in noms:
            open(os.path.join(self.dir, n), "w").close()

    def test_nom_libre_inchange(self):
        self.assertEqual(unique_path(self.dir, "film.mp4"), "film.mp4")

    def test_premier_doublon(self):
        self.pose("film.mp4")
        self.assertEqual(unique_path(self.dir, "film.mp4"), "film (1).mp4")

    def test_repart_de_la_racine(self):
        self.pose("film.mp4", "film (1).mp4", "film (2).mp4", "film (3).mp4")
        self.assertEqual(unique_path(self.dir, "film (3).mp4"), "film (4).mp4")
        self.assertEqual(unique_path(self.dir, "film.mp4"), "film (4).mp4")

    def test_numero_legitime_conserve(self):
        """« Matrix (2) » est un titre, pas un doublon : libre, on n'y touche pas."""
        self.pose("Matrix.mp4")
        self.assertEqual(unique_path(self.dir, "Matrix (2).mp4"), "Matrix (2).mp4")

    def test_parentheses_qui_ne_sont_pas_un_numero(self):
        self.pose("film (final).mp4")
        self.assertEqual(unique_path(self.dir, "film (final).mp4"), "film (final) (1).mp4")

    def test_part_et_pydm_comptent(self):
        self.pose("film.mp4.part", "film (1).mp4.pydm")
        self.assertEqual(unique_path(self.dir, "film.mp4"), "film (2).mp4")
