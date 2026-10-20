import os
import stat
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

from pydm.engine import VideoDownload


class FakeYoutubeDL:
    """Imite yt_dlp.YoutubeDL : enregistre les options et l'état du fichier de cookies pendant l'appel."""
    seen = {}

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True):
        path = self.opts.get("cookiefile")
        FakeYoutubeDL.seen = {"opts": dict(self.opts), "cookiefile": path}
        if path:
            FakeYoutubeDL.seen["mode"] = stat.S_IMODE(os.stat(path).st_mode)
            with open(path) as f:
                FakeYoutubeDL.seen["content"] = f.read()
        return {}


class VideoCookiesTest(unittest.TestCase):
    def run_video(self, url, headers, browser="Aucun"):
        fake = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {"yt_dlp": fake}):
            d = VideoDownload(url, tmp, headers=headers, browser=browser)
            d.start()
            end = time.time() + 10
            while d.running and time.time() < end:
                time.sleep(0.02)
        return d, FakeYoutubeDL.seen

    def test_cookies_en_fichier_et_non_en_entete(self):
        d, seen = self.run_video("https://www.youtube.com/watch?v=abc",
                                 {"User-Agent": "Firefox", "Cookie": "SID=1; PREF=f6=8"})
        self.assertEqual(d.status, "Terminé", d.status)
        self.assertNotIn("Cookie", seen["opts"].get("http_headers", {}))
        self.assertEqual(seen["opts"]["http_headers"]["User-Agent"], "Firefox")
        self.assertEqual(seen["mode"], 0o600)
        lines = [l.split("\t") for l in seen["content"].splitlines() if l and not l.startswith("#")]
        self.assertEqual([(l[0], l[5], l[6]) for l in lines],
                         [(".youtube.com", "SID", "1"), (".youtube.com", "PREF", "f6=8")])
        self.assertFalse(os.path.exists(seen["cookiefile"]))      # supprimé après usage

    def test_sans_cookie_pas_de_fichier(self):
        _, seen = self.run_video("https://vimeo.com/1", {"User-Agent": "Firefox"})
        self.assertIsNone(seen["cookiefile"])

    def test_cookies_du_navigateur_prioritaires(self):
        _, seen = self.run_video("https://www.youtube.com/watch?v=abc",
                                 {"User-Agent": "Firefox", "Cookie": "SID=1"}, browser="firefox")
        self.assertIsNone(seen["cookiefile"])
        self.assertEqual(seen["opts"]["cookiesfrombrowser"], ("firefox",))
        self.assertNotIn("Cookie", seen["opts"]["http_headers"])


if __name__ == "__main__":
    unittest.main()
