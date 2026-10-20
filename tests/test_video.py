import os
import stat
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

from pydm.engine import VideoDownload, ytdlp_attempts


class FakeYoutubeDL:
    """Imite yt_dlp.YoutubeDL : enregistre chaque essai ; `refuse` simule les échecs."""
    calls = []
    refuse = staticmethod(lambda opts: None)     # renvoie un message d'erreur pour faire échouer l'essai

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True):
        call = {"opts": dict(self.opts), "cookiefile": self.opts.get("cookiefile")}
        if call["cookiefile"]:
            call["mode"] = stat.S_IMODE(os.stat(call["cookiefile"]).st_mode)
            with open(call["cookiefile"]) as f:
                call["content"] = f.read()
        FakeYoutubeDL.calls.append(call)
        error = FakeYoutubeDL.refuse(self.opts)
        if error:
            raise Exception(error)
        return {}


class VideoCookiesTest(unittest.TestCase):
    def run_video(self, url, headers, browser="Aucun", refuse=None, **kw):
        FakeYoutubeDL.calls = []
        FakeYoutubeDL.refuse = staticmethod(refuse or (lambda opts: None))
        fake = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {"yt_dlp": fake}):
            d = VideoDownload(url, tmp, headers=headers, browser=browser, **kw)
            d.start()
            end = time.time() + 10
            while d.running and time.time() < end:
                time.sleep(0.02)
        return d, FakeYoutubeDL.calls

    def test_essai_sans_cookies_d_abord(self):
        d, calls = self.run_video("https://www.youtube.com/watch?v=abc",
                                  {"User-Agent": "Firefox", "Cookie": "SID=1"})
        self.assertEqual(d.status, "Terminé", d.status)
        self.assertEqual(len(calls), 1)
        self.assertIsNone(calls[0]["cookiefile"])
        self.assertEqual(calls[0]["opts"]["http_headers"], {"User-Agent": "Firefox"})

    def test_reessai_avec_cookies_en_fichier(self):
        d, calls = self.run_video("https://www.youtube.com/watch?v=abc",
                                  {"User-Agent": "Firefox", "Cookie": "SID=1; PREF=f6=8"},
                                  refuse=lambda o: None if o.get("cookiefile") else "Sign in to confirm your age")
        self.assertEqual(d.status, "Terminé", d.status)
        self.assertEqual([c["cookiefile"] is not None for c in calls], [False, True])
        second = calls[1]
        self.assertNotIn("Cookie", second["opts"]["http_headers"])
        self.assertEqual(second["mode"], 0o600)
        lines = [l.split("\t") for l in second["content"].splitlines() if l and not l.startswith("#")]
        self.assertEqual([(l[0], l[5], l[6]) for l in lines],
                         [(".youtube.com", "SID", "1"), (".youtube.com", "PREF", "f6=8")])
        self.assertFalse(os.path.exists(second["cookiefile"]))      # supprimé après usage

    def test_deux_echecs_garde_le_premier_message(self):
        d, calls = self.run_video("https://www.youtube.com/watch?v=abc", {"Cookie": "SID=1"},
                                  refuse=lambda o: "page reload" if o.get("cookiefile") else "Sign in to confirm")
        self.assertEqual(len(calls), 2)
        self.assertEqual(d.status, "Erreur : Sign in to confirm")
        self.assertFalse(os.path.exists(calls[1]["cookiefile"]))

    def test_sans_cookie_un_seul_essai(self):
        d, calls = self.run_video("https://vimeo.com/1", {"User-Agent": "Firefox"}, refuse=lambda o: "boom")
        self.assertEqual(len(calls), 1)
        self.assertEqual(d.status, "Erreur : boom")

    def test_navigateur_choisi_en_second_essai(self):
        d, calls = self.run_video("https://www.youtube.com/watch?v=abc",
                                  {"User-Agent": "Firefox", "Cookie": "SID=1"}, browser="firefox")
        self.assertEqual(d.status, "Terminé", d.status)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("cookiesfrombrowser", calls[0]["opts"])

    def test_navigateur_choisi_si_le_premier_echoue(self):
        _, calls = self.run_video("https://www.youtube.com/watch?v=abc",
                                  {"User-Agent": "Firefox", "Cookie": "SID=1"}, browser="firefox",
                                  refuse=lambda o: "boom")
        self.assertEqual(len(calls), 2)
        self.assertNotIn("cookiesfrombrowser", calls[0]["opts"])
        self.assertEqual(calls[1]["opts"]["cookiesfrombrowser"], ("firefox",))
        self.assertIsNone(calls[1]["cookiefile"])         # le navigateur choisi remplace ceux de l'extension
        self.assertNotIn("Cookie", calls[1]["opts"]["http_headers"])

    @unittest.skipIf(os.geteuid() == 0, "root peut écrire partout")
    def test_dossier_impossible_a_creer(self):
        FakeYoutubeDL.calls = []
        FakeYoutubeDL.refuse = staticmethod(lambda opts: None)
        fake = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {"yt_dlp": fake}):
            locked = os.path.join(tmp, "verrou")
            os.mkdir(locked, 0o500)
            try:
                d = VideoDownload("https://vimeo.com/1", os.path.join(locked, "sous-dossier"))
                d.start()
                d.wait(5)
            finally:
                os.chmod(locked, 0o700)
        self.assertTrue(d.status.startswith("Erreur"), d.status)


    def test_format_choisi(self):
        _, calls = self.run_video("https://vimeo.com/1", {}, fmt="137+140")
        self.assertEqual(calls[0]["opts"]["format"], "137+140/bv*+ba/b")     # repli si le format a disparu

    def test_nom_choisi(self):
        d, calls = self.run_video("https://vimeo.com/1", {}, stem="Ma vidéo/été")
        self.assertEqual(calls[0]["opts"]["outtmpl"], os.path.join(d.folder, "Ma vidéo_été.%(ext)s"))

    def test_nom_vide_garde_le_modele(self):
        _, calls = self.run_video("https://vimeo.com/1", {}, stem="  ")
        self.assertTrue(calls[0]["opts"]["outtmpl"].endswith("%(title).150B [%(id)s].%(ext)s"))


    def test_nom_long_tronque(self):
        d, calls = self.run_video("https://vimeo.com/1", {}, stem="漢" * 120)
        base = os.path.basename(calls[0]["opts"]["outtmpl"])[:-len(".%(ext)s")]
        self.assertLessEqual(len(base.encode()), 150)
        self.assertTrue(base.startswith("漢"))

    def test_pourcent_echappe(self):
        _, calls = self.run_video("https://vimeo.com/1", {}, stem="100% Hits %(uploader)s")
        self.assertTrue(calls[0]["opts"]["outtmpl"].endswith("100%% Hits %%(uploader)s.%(ext)s"))


    def test_make_download_range_les_videos(self):
        from pydm.engine import make_download
        route = lambda cat: "/dl/" + cat  # noqa: E731
        fake = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        with mock.patch.dict(sys.modules, {"yt_dlp": fake}):
            v = make_download("https://youtube.com/watch?v=1", "/dl", kind="video", route=route)
            a = make_download("https://youtube.com/watch?v=1", "/dl", quality="Audio MP3", kind="video", route=route)
        self.assertEqual((v.folder, a.folder), ("/dl/video", "/dl/music"))


    def test_hook_freine(self):
        d = VideoDownload("https://vimeo.com/1", "/tmp")
        reports = (("v.mp4", 800 * 2 ** 20), ("v.mp4", 800 * 2 ** 20 + 2000),   # reprise : déjà 800 Mo
                   ("a.m4a", 500), ("a.m4a", 900), ("a.m4a", 800))               # nouveau fichier, puis désordre
        with mock.patch("pydm.engine.LIMITER") as lim:
            for name, n in reports:
                d._hook({"status": "downloading", "downloaded_bytes": n, "filename": name})
        self.assertEqual([c.args[0] for c in lim.consume.call_args_list], [2000, 400])


    def test_sans_ytdlp_erreur(self):
        from pydm.scheduler import Scheduler
        from datetime import datetime
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {"yt_dlp": None}):
            d = VideoDownload("https://vimeo.com/1", tmp)
            s = Scheduler(3)
            for _ in range(5):
                s.tick([d], datetime.now())
                d.wait(2)
        self.assertTrue(d.error)
        self.assertEqual(d.want, "stop")


    def test_fichiers_intermediaires(self):
        with tempfile.TemporaryDirectory() as tmp:
            names = ["Clip.mp4", "Clip.f137.mp4.part", "Clip.f140.m4a", "Clip.mp4.ytdl", "Autre.mp4",
                     "Clip.mkv", "Clip.srt", "Clip.pdf"]          # fichiers de l'utilisateur au même nom
            for n in names:
                open(os.path.join(tmp, n), "w").close()
            d = VideoDownload("https://vimeo.com/1", tmp, name="Clip.mp4")
            self.assertEqual(sorted(os.path.basename(f) for f in d.files()), sorted(names[:4]))
            pending = VideoDownload("https://vimeo.com/1", tmp, stem="Clip")
            self.assertEqual(sorted(os.path.basename(f) for f in pending.files()),
                             ["Clip.f137.mp4.part", "Clip.f140.m4a", "Clip.mp4.ytdl"])


    def test_vieux_fichiers_de_cookies_nettoyes(self):
        import time as _time
        from pydm.engine import clean_stale_cookie_files
        with tempfile.TemporaryDirectory() as tmp:
            old, recent, other = (os.path.join(tmp, n) for n in
                                  ("pydm-cookies-a.txt", "pydm-cookies-b.txt", "autre.txt"))
            for p in (old, recent, other):
                open(p, "w").close()
            past = _time.time() - 7200
            os.utime(old, (past, past))
            os.utime(other, (past, past))
            clean_stale_cookie_files(tmpdir=tmp)
            self.assertEqual((os.path.exists(old), os.path.exists(recent), os.path.exists(other)),
                             (False, True, True))


class AttemptsTest(unittest.TestCase):
    def test_ytdlp_attempts_sans_cookies(self):
        self.assertEqual(list(ytdlp_attempts("https://a.fr/v", {"User-Agent": "x"}, "Aucun")), [{}])

    def test_ytdlp_attempts_fichier_supprime(self):
        g = ytdlp_attempts("https://a.fr/v", {"Cookie": "a=1"}, "Aucun")
        self.assertEqual(next(g), {})
        opts = next(g)
        self.assertTrue(os.path.exists(opts["cookiefile"]))
        g.close()
        self.assertFalse(os.path.exists(opts["cookiefile"]))

    def test_ytdlp_attempts_navigateur(self):
        self.assertEqual(list(ytdlp_attempts("https://a.fr/v", {}, "firefox")),
                         [{}, {"cookiesfrombrowser": ("firefox",)}])


if __name__ == "__main__":
    unittest.main()
