import os
import shutil
import sys
import tempfile
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

    def test_video_sans_hauteur_avec_audio(self):
        info = {"formats": [fmt("hls-1", "mp4", "avc1", "none"), fmt("a", "m4a", "none", "mp4a", tbr=128)]}
        choices, _ = build_choices(info, ffmpeg=True)
        self.assertEqual([c["label"] for c in choices], ["Meilleure disponible", "Audio seul · MP3"])
        self.assertEqual(choices[0]["format"], "bv*+ba/b")

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

    def test_analyze_403_explicite(self):
        r = self.video(refuse=lambda o: "ERROR: HTTP Error 403: Forbidden")
        self.assertIn("Accès refusé par le serveur", r["error"])

    def test_analyze_fichier(self):
        data = os.urandom(300_000)
        url, stop = serve(data, headers={"Content-Disposition": "attachment; filename=a.zip"})
        self.addCleanup(stop)
        r = analyze(url + "/x", kind="file")
        self.assertEqual((r["kind"], r["name"], r["size"], r["resumable"], r["choices"]),
                         ("file", "a.zip", len(data), True, []))

    def test_analyze_expose_l_echeance(self):
        import time as _time
        data = os.urandom(1000)
        url, stop = serve(data)
        self.addCleanup(stop)
        limite = int(_time.time() + 600)
        r = analyze(url + "/x?Expires=%d&Signature=ab" % limite, kind="file")
        self.assertEqual((r["kind"], r["expires"]), ("file", float(limite)))
        self.assertIsNone(analyze(url + "/x", kind="file")["expires"])

    def test_analyze_fichier_injoignable(self):
        r = analyze("http://127.0.0.1:9/x", kind="file")
        self.assertEqual(r["kind"], "error")
        self.assertTrue(r["error"])


class RealWorldChoicesTest(unittest.TestCase):
    def test_audio_langue_originale(self):
        info = {"duration": 100, "formats": [
            fmt("137", "mp4", "avc1", "none", 1080, 4000, filesize=10),
            fmt("140-8", "m4a", "none", "mp4a", tbr=130, filesize=1, language="es", language_preference=-1),
            fmt("140-23", "m4a", "none", "mp4a", tbr=129, filesize=1, language="en", language_preference=10)]}
        for ffmpeg in (True, False):
            choices, _ = build_choices(dict(info, formats=info["formats"] + [
                fmt("18", "mp4", "avc1", "mp4a", 360, 500, filesize=5)]), ffmpeg=ffmpeg)
            audio_rows = [c for c in choices if c["audio_only"]]
            if ffmpeg:
                self.assertEqual(choices[0]["format"], "137+140-23")
            else:
                self.assertEqual(audio_rows[0]["format"], "140-23")

    def test_dash_prefere_a_hls(self):
        info = {"duration": 240, "formats": [
            fmt("270", "mp4", "avc1.640028", "none", 1080, 5000, protocol="m3u8_native"),
            fmt("137", "mp4", "avc1.640028", "none", 1080, 3300, protocol="https", filesize=99_700_000),
            fmt("603", "mp4", "vp09.00.11.08", "none", 144, 990, protocol="m3u8_native"),
            fmt("160", "mp4", "avc1.4d400c", "none", 144, 110, protocol="https", filesize=2_000_000),
            fmt("140", "m4a", "none", "mp4a.40.2", tbr=129, protocol="https", filesize=3_900_000)]}
        choices, _ = build_choices(info, ffmpeg=True)
        self.assertEqual(choices[0]["format"], "137+140")
        self.assertEqual(choices[0]["label"], f"1080p · MP4 · {human(103_600_000)}")
        self.assertEqual(choices[1]["format"], "160+140")

    def test_mp4_signifie_h264(self):
        info = {"formats": [fmt("399", "mp4", "av01.0.08M.08", "none", 1080, 2000),
                            fmt("248", "webm", "vp9", "none", 1080, 2100),
                            fmt("251", "webm", "none", "opus", tbr=160)]}
        choices, _ = build_choices(info, ffmpeg=True)
        self.assertEqual(choices[0]["format"], "248+251")
        self.assertEqual(choices[0]["label"], "1080p · WEBM")


if __name__ == "__main__":
    unittest.main()


class PremiereImageTest(unittest.TestCase):
    """Beaucoup de sites ne donnent aucune miniature : on prend la première image du flux."""

    def test_ligne_de_commande(self):
        from pydm.analyze import frame_args
        args = frame_args("ffmpeg", "https://a.fr/v.m3u8", {"Referer": "https://a.fr/p", "Cookie": "S=1"})
        self.assertLess(args.index("-headers"), args.index("-i"), "en-têtes après -i : ignorés")
        self.assertIn("Referer: https://a.fr/p\r\n", args[args.index("-headers") + 1])
        self.assertEqual(args[args.index("-i") + 1], "https://a.fr/v.m3u8")
        self.assertEqual(args[-1], "-")
        self.assertIn("-frames:v", args)
        sans = frame_args("ffmpeg", "https://a.fr/v.mp4", None, at=0)
        self.assertNotIn("-headers", sans)
        self.assertNotIn("-ss", sans)

    def test_deux_essais_puis_abandon(self):
        from pydm.analyze import first_frame
        vus = []

        class Sortie:
            def __init__(self, data):
                self.stdout = data
        # rien à 2 s (flux trop court), une image à 0 s
        def runner(args):
            vus.append(args[args.index("-ss") + 1] if "-ss" in args else "0")
            return Sortie(b"\xff\xd8ancre" if "-ss" not in args else b"")
        self.assertEqual(first_frame("https://a.fr/v.mp4", ffmpeg="ffmpeg", runner=runner),
                         b"\xff\xd8ancre")
        self.assertEqual(vus, ["2", "0"])
        self.assertIsNone(first_frame("https://a.fr/v.mp4", ffmpeg="ffmpeg",
                                      runner=lambda a: Sortie(b"")))
        self.assertIsNone(first_frame("https://a.fr/v.mp4", ffmpeg="ffmpeg",
                                      runner=lambda a: Sortie(b"<html>pas une image")))

    def test_sans_ffmpeg_ni_lien(self):
        from pydm.analyze import first_frame
        self.assertIsNone(first_frame("https://a.fr/v.mp4", ffmpeg=""))
        self.assertIsNone(first_frame("", ffmpeg="ffmpeg"))

    def test_erreur_de_ffmpeg_silencieuse(self):
        from pydm.analyze import first_frame
        def boum(args):
            raise OSError("ffmpeg introuvable")
        self.assertIsNone(first_frame("https://a.fr/v.mp4", ffmpeg="ffmpeg", runner=boum))

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg absent")
    def test_vraie_image_d_une_vraie_video(self):
        import subprocess as sp
        from pydm.analyze import first_frame
        with tempfile.TemporaryDirectory() as tmp:
            video = os.path.join(tmp, "essai.mp4")
            sp.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10",
                    "-t", "4", "-pix_fmt", "yuv420p", video], check=True, timeout=60)
            data = first_frame(video)
        self.assertTrue(data and data[:2] == b"\xff\xd8", "JPEG attendu")
        self.assertLess(len(data), 64 * 1024)
