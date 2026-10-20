import os
import sys
import types
import unittest
from unittest import mock

from pydm.analyze import analyze, build_choices, preselect
from pydm.util import human
from tests.httpserver import serve


def fmt(fid, ext, vcodec, acodec, height=None, tbr=None, **kw):
    return dict(format_id=fid, ext=ext, vcodec=vcodec, acodec=acodec, height=height, tbr=tbr, **kw)


YT_INFO = {
    "title": "Conf/2026", "duration": 2538, "webpage_url_domain": "youtube.com",
    "formats": [
        fmt("sb0", "mhtml", "none", "none", format_note="storyboard"),
        fmt("137", "mp4", "avc1.640028", "none", 1080, 4000, filesize=400_000_000),
        fmt("248", "webm", "vp9", "none", 1080, 4200, filesize=380_000_000),
        fmt("136", "mp4", "avc1.4d401f", "none", 720, 2000, filesize_approx=190_000_000),
        fmt("135", "mp4", "avc1.4d401e", "none", 480),
        fmt("140", "m4a", "none", "mp4a.40.2", tbr=128, filesize=12_000_000),
        fmt("251", "webm", "none", "opus", tbr=160, filesize=15_000_000),
        fmt("18", "mp4", "avc1.42001E", "mp4a.40.2", 360, 600, filesize=30_000_000),
    ],
}


class ChoicesTest(unittest.TestCase):
    def test_choix_avec_ffmpeg(self):
        choices, missing = build_choices(YT_INFO, ffmpeg=True)
        self.assertEqual([c["label"] for c in choices], [
            f"1080p · MP4 · {human(412_000_000)}", f"720p · MP4 · ≈ {human(202_000_000)}",
            "480p · MP4", f"360p · MP4 · {human(30_000_000)}", "Audio seul · MP3"])
        self.assertEqual(choices[0]["format"], "137+140")
        self.assertEqual(choices[3]["format"], "18")
        self.assertIs(choices[0]["approx"], False)
        self.assertIs(choices[1]["approx"], True)
        self.assertTrue(choices[-1]["audio_only"])
        self.assertIs(missing, False)

    def test_choix_sans_ffmpeg(self):
        choices, missing = build_choices(YT_INFO, ffmpeg=False)
        self.assertEqual([c["label"] for c in choices],
                         [f"360p · MP4 · {human(30_000_000)}", f"Audio seul · WEBM · {human(15_000_000)}"])
        self.assertEqual((choices[0]["format"], choices[1]["format"]), ("18", "251"))
        self.assertIs(missing, True)

    def test_aucun_format(self):
        for ffmpeg, selector in ((True, "bv*+ba/b"), (False, "b")):
            choices, _ = build_choices({"formats": []}, ffmpeg=ffmpeg)
            self.assertEqual([(c["label"], c["format"]) for c in choices], [("Meilleure disponible", selector)])

    def test_sans_taille_ni_duree(self):
        info = {"formats": [fmt("22", "mp4", "avc1", "none", 720)]}
        choices, _ = build_choices(info, ffmpeg=True)
        self.assertEqual([c["label"] for c in choices], ["720p · MP4", "Audio seul · MP3"])

    def test_preselection(self):
        choices, _ = build_choices(YT_INFO, ffmpeg=True)
        self.assertEqual(preselect(choices, "Meilleure"), 0)
        self.assertEqual(preselect(choices, "720p"), 1)
        self.assertEqual(preselect(choices, "Audio MP3"), len(choices) - 1)
        self.assertEqual(preselect(choices, "inconnue"), 0)
        low = [c for c in choices if c["height"] in (720, 480)] + [choices[-1]]
        self.assertEqual(preselect(low, "1080p"), 0)


class FakeYoutubeDL:
    calls = []
    refuse = staticmethod(lambda opts: None)
    info = YT_INFO

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True):
        FakeYoutubeDL.calls.append(dict(self.opts, download=download))
        error = FakeYoutubeDL.refuse(self.opts)
        if error:
            raise Exception(error)
        return FakeYoutubeDL.info


class AnalyzeTest(unittest.TestCase):
    def video(self, refuse=None, headers=None):
        FakeYoutubeDL.calls = []
        FakeYoutubeDL.refuse = staticmethod(refuse or (lambda opts: None))
        fake = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        with mock.patch.dict(sys.modules, {"yt_dlp": fake}):
            return analyze("https://www.youtube.com/watch?v=x", headers, kind="video", ffmpeg=True)

    def test_analyze_video(self):
        r = self.video()
        self.assertEqual(r["kind"], "video")
        self.assertEqual(r["name"], "Conf_2026.mp4")
        self.assertEqual(r["selected"], 0)
        self.assertEqual(r["size"], 412_000_000)
        self.assertEqual((r["title"], r["duration"], r["site"]), ("Conf/2026", 2538, "youtube.com"))
        self.assertIs(FakeYoutubeDL.calls[0]["download"], False)
        self.assertNotIn("Cookie", FakeYoutubeDL.calls[0].get("http_headers", {}))

    def test_analyze_cookies_en_second(self):
        r = self.video(refuse=lambda o: None if o.get("cookiefile") else "page reload",
                       headers={"Cookie": "SID=1"})
        self.assertEqual(len(FakeYoutubeDL.calls), 2)
        self.assertEqual(r["kind"], "video")

    def test_analyze_erreur_et_drm(self):
        r = self.video(refuse=lambda o: "ERROR: HTTP Error 404: Not Found")
        self.assertEqual(r["kind"], "error")
        self.assertIn("404", r["error"])
        self.assertNotIn("ERROR:", r["error"])
        r = self.video(refuse=lambda o: "This video is DRM protected")
        self.assertIs(r["drm"], True)

    def test_analyze_fichier(self):
        data = os.urandom(300_000)
        url, stop = serve(data, headers={"Content-Disposition": "attachment; filename=a.zip"})
        self.addCleanup(stop)
        r = analyze(url + "/x", kind="file")
        self.assertEqual((r["kind"], r["name"], r["size"], r["resumable"], r["choices"]),
                         ("file", "a.zip", len(data), True, []))

    def test_analyze_fichier_injoignable(self):
        r = analyze("http://127.0.0.1:9/x", kind="file")
        self.assertEqual(r["kind"], "error")
        self.assertTrue(r["error"])


if __name__ == "__main__":
    unittest.main()
