import unittest

import os
from unittest import mock

from pydm.util import expand_path, safe_filename

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
