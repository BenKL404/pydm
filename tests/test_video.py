import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

from pydm.engine import VideoDownload, ytdlp_attempts


class FakeYoutubeDL:
    """Imite yt_dlp.YoutubeDL : enregistre chaque essai ; `refuse` simule les échecs."""
    calls = []
    refuse = staticmethod(lambda opts: None)     # renvoie un message d'erreur pour faire échouer l'essai
    creates = False                              # écrit vraiment le fichier de sortie (noms uniques)

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
        if FakeYoutubeDL.creates:
            home = (self.opts.get("paths") or {}).get("home", "")
            path = os.path.join(home, self.opts["outtmpl"].replace("%(ext)s", "mp4"))
            with open(path, "w") as f:
                f.write("video")
            return {"requested_downloads": [{"filepath": path}]}
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
        if os.name != "nt":                         # Windows : droits hérités du dossier temporaire
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

    @unittest.skipIf(os.name == "nt" or getattr(os, "geteuid", lambda: -1)() == 0, "droits POSIX (root ou Windows)")
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
        for ffmpeg, fallback in (("/usr/bin/ffmpeg", "bv*+ba/b"), (None, "b")):   # repli si le format a disparu
            with mock.patch("pydm.engine.shutil.which", return_value=ffmpeg):
                _, calls = self.run_video("https://vimeo.com/1", {}, fmt="137+140")
            self.assertEqual(calls[0]["opts"]["format"], f"137+140/{fallback}")

    def test_nom_choisi(self):
        d, calls = self.run_video("https://vimeo.com/1", {}, stem="Ma vidéo/été")
        self.assertEqual(calls[0]["opts"]["outtmpl"], "Ma vidéo_été.%(ext)s")
        self.assertEqual(calls[0]["opts"]["paths"]["home"], d.folder)

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

    def test_hook_limite_de_la_video(self):
        d = VideoDownload("https://vimeo.com/1", "/tmp")
        d.limit_kbps = 300
        with mock.patch("pydm.engine.LIMITER") as lim, mock.patch.object(d.limiter, "consume") as own:
            for n in (1000, 3000):
                d._hook({"status": "downloading", "downloaded_bytes": n, "filename": "v.mp4"})
        self.assertEqual([c.args[0] for c in own.call_args_list], [2000])
        self.assertEqual([c.args[0] for c in lim.consume.call_args_list], [2000])
        from pydm.engine import entry_from_task, task_from_entry
        self.assertEqual(task_from_entry(entry_from_task(d)).limit_kbps, 300)


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


    def test_message_403_explicite(self):
        d, _ = self.run_video("https://exemple.fr/master.m3u8", {}, refuse=lambda o: (
            "ERROR: [generic] master: Unable to download webpage: HTTP Error 403: Forbidden"))
        self.assertIn("Accès refusé par le serveur", d.status)
        self.assertIn("Rechargez la page", d.error)

    def test_message_lien_expire(self):
        from pydm.engine import friendly_error
        perime = "https://a.fr/f.bin?Expires=%d&Signature=x" % int(time.time() - 60)
        frais = "https://a.fr/f.bin?Expires=%d&Signature=x" % int(time.time() + 3600)
        self.assertTrue(friendly_error("HTTP Error 403: Forbidden", url=perime)
                        .startswith("Ce lien a expiré"))
        self.assertTrue(friendly_error("HTTP Error 403: Forbidden", url=frais)
                        .startswith("Accès refusé par le serveur (403)"))
        self.assertTrue(friendly_error("HTTP Error 403: Forbidden")
                        .startswith("Accès refusé par le serveur (403)"))

    def test_message_ordinaire_inchange(self):
        from pydm.engine import friendly_error
        self.assertEqual(friendly_error("HTTP Error 404: Not Found"), "HTTP Error 404: Not Found")
        self.assertTrue(friendly_error("HTTP Error 403: Forbidden").startswith("Accès refusé par le serveur (403)"))


    def test_fragments_manquants_refuses(self):
        """Un fragment indisponible doit faire échouer la vidéo, pas livrer un fichier troué."""
        _, calls = self.run_video("https://exemple.fr/master.m3u8", {}, parts=5)
        opts = calls[0]["opts"]
        self.assertIs(opts["skip_unavailable_fragments"], False)
        self.assertEqual(opts["concurrent_fragment_downloads"], 5)
        sleep = opts["retry_sleep_functions"]["fragment"]
        self.assertEqual([sleep(1), sleep(4), sleep(9)], [2, 16, 30])


    def test_fichiers_temporaires_a_l_ecart(self):
        """Fragments et .part ne doivent pas encombrer le dossier de téléchargement.

        yt-dlp **ignore** `paths` quand le modèle de nom est un chemin absolu : c'est tout
        l'objet de ce test, le réglage seul ne suffit pas.
        """
        d, calls = self.run_video("https://exemple.fr/master.m3u8", {})
        opts = calls[0]["opts"]
        chemins = opts["paths"]
        self.assertEqual(chemins["home"], d.folder)
        self.assertEqual(os.path.dirname(chemins["temp"]), d.folder)
        self.assertTrue(os.path.basename(chemins["temp"]).startswith("."), chemins["temp"])
        self.assertFalse(os.path.isabs(opts["outtmpl"]),
                         "modèle absolu : yt-dlp ignorerait paths et sèmerait ses fragments")
        self.assertNotIn(os.sep, opts["outtmpl"])

    def test_dossier_temporaire_nettoye(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = VideoDownload("https://vimeo.com/1", tmp)
            reste = d.temp_dir()
            os.makedirs(reste, exist_ok=True)
            d.clean_temp()
            self.assertFalse(os.path.exists(reste), "dossier vide : à supprimer")
            os.makedirs(reste, exist_ok=True)
            open(os.path.join(reste, "Clip.mp4.part"), "w").close()
            d.clean_temp()
            self.assertTrue(os.path.exists(reste), "des restes : on ne jette rien")

    def test_fichiers_intermediaires_du_dossier_temporaire(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = VideoDownload("https://vimeo.com/1", tmp, name="Clip.mp4")
            os.makedirs(d.temp_dir(), exist_ok=True)
            cache = os.path.join(d.temp_dir(), "Clip.f137.mp4.part")
            open(cache, "w").close()
            open(os.path.join(tmp, "Clip.mp4"), "w").close()
            self.assertIn(cache, d.files())

    def test_dossier_temporaire_supprime_apres_coup(self):
        """Rien ne doit rester dans le dossier de destination une fois la vidéo récupérée."""
        FakeYoutubeDL.calls = []
        FakeYoutubeDL.refuse = staticmethod(lambda opts: None)
        fake = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {"yt_dlp": fake}):
            d = VideoDownload("https://vimeo.com/1", tmp)
            d.start()
            d.wait(10)
            self.assertEqual(d.status, "Terminé", d.status)
            self.assertEqual(os.listdir(tmp), [], "le dossier doit être propre")

    def test_progression_sans_retour_en_arriere(self):
        """Vidéo puis audio : le compteur ne doit pas repartir de zéro à chaque flux."""
        d = VideoDownload("https://vimeo.com/1", "/tmp")
        vus = []
        with mock.patch("pydm.engine.LIMITER"):
            for nom, got, total in (("v.mp4", 1_000_000, 4_000_000), ("v.mp4", 4_000_000, 4_000_000),
                                    ("a.m4a", 100_000, 500_000), ("a.m4a", 500_000, 500_000)):
                d._hook({"status": "downloading", "downloaded_bytes": got,
                         "total_bytes": total, "filename": nom})
                vus.append((d.done, d.size))
        self.assertEqual([x[0] for x in vus], sorted(x[0] for x in vus), "progression en arrière")
        self.assertEqual([x[1] for x in vus], sorted(x[1] for x in vus), "taille annoncée en baisse")
        self.assertEqual(vus[-1], (4_500_000, 4_500_000))


    def test_nom_libre_quelle_que_soit_l_extension(self):
        from pydm.engine import unique_stem
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(unique_stem(tmp, "Film"), "Film")
            open(os.path.join(tmp, "Film.mp4"), "w").close()
            self.assertEqual(unique_stem(tmp, "Film"), "Film (1)")
            open(os.path.join(tmp, "Film (1).mkv"), "w").close()
            self.assertEqual(unique_stem(tmp, "Film"), "Film (2)")
            # un nom déjà réservé par une autre vidéo en cours compte autant qu'un fichier
            self.assertEqual(unique_stem(tmp, "Film", taken={"Film (2)"}), "Film (3)")
            self.assertEqual(unique_stem(tmp, "Autre"), "Autre")

    def test_numerotation_repart_de_la_racine(self):
        """« Film (3) » occupé donne « Film (4) », pas « Film (3) (1) »."""
        from pydm.engine import unique_stem
        with tempfile.TemporaryDirectory() as tmp:
            for n in ("Film.mp4", "Film (1).mp4", "Film (2).mkv"):
                open(os.path.join(tmp, n), "w").close()
            self.assertEqual(unique_stem(tmp, "Film"), "Film (3)")
            self.assertEqual(unique_stem(tmp, "Film", taken={"Film (3)"}), "Film (4)")
            self.assertEqual(unique_stem(tmp, "Film (3)", taken={"Film (3)"}), "Film (4)")
            self.assertEqual(unique_stem(tmp, "Film (3)", taken={"Film (3)", "Film (4)"}), "Film (5)")
            self.assertEqual(unique_stem(tmp, "Matrix (2)"), "Matrix (2)")   # titre, pas doublon

    def test_trois_videos_de_suite_apres_des_fichiers_existants(self):
        """Le cas vu à l'écran : trois ajouts alors que trois fichiers du même nom sont déjà là."""
        from pydm.engine import unique_stem
        with tempfile.TemporaryDirectory() as tmp:
            for n in ("Série.mp4", "Série (1).mp4", "Série (2).mp4"):
                open(os.path.join(tmp, n), "w").close()
            pris, noms = set(), []
            for _ in range(3):
                nom = unique_stem(tmp, "Série (3)", pris)      # nom déjà numéroté par la fenêtre
                pris.add(nom)
                noms.append(nom)
        self.assertEqual(noms, ["Série (3)", "Série (4)", "Série (5)"])

    def test_videos_simultanees_noms_distincts(self):
        """Trois vidéos du même titre lancées ensemble ne doivent pas viser le même fichier."""
        import threading
        FakeYoutubeDL.calls = []
        barriere = threading.Barrier(3)

        def attendre(opts):     # toutes dans yt-dlp en même temps : le pire des cas
            barriere.wait(10)
            return None
        FakeYoutubeDL.refuse = staticmethod(attendre)
        fake = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {"yt_dlp": fake}):
            taches = [VideoDownload("https://exemple.fr/%d" % i, tmp, stem="Le Jeu de pouvoir")
                      for i in range(3)]
            for t in taches:
                t.start()
            for t in taches:
                t.wait(15)
        modeles = sorted(os.path.basename(c["opts"]["outtmpl"]) for c in FakeYoutubeDL.calls)
        self.assertEqual(len(set(modeles)), 3, modeles)
        self.assertEqual(modeles[0], "Le Jeu de pouvoir (1).%(ext)s")


    def test_taille_estimee_sur_les_fragments(self):
        """Pour un HLS, débit × durée est très faux : on extrapole sur les fragments reçus."""
        d = VideoDownload("https://exemple.fr/master.m3u8", "/tmp")
        with mock.patch("pydm.engine.LIMITER"):
            d._hook({"status": "downloading", "downloaded_bytes": 10_000_000,
                     "total_bytes_estimate": 2_300_000_000, "filename": "v.mp4"})
            self.assertEqual((d.size, d.size_approx), (2_300_000_000, True))   # rien de mieux encore
            for index, got in ((4, 40_000_000), (40, 400_000_000)):
                d._hook({"status": "downloading", "downloaded_bytes": got, "filename": "v.mp4",
                         "total_bytes_estimate": 2_300_000_000,
                         "fragment_index": index, "fragment_count": 100})
        self.assertEqual((d.size, d.size_approx), (1_000_000_000, True))       # 400 Mo pour 40 %
        with mock.patch("pydm.engine.LIMITER"):
            d._hook({"status": "downloading", "downloaded_bytes": 500_000_000,
                     "total_bytes": 980_000_000, "filename": "v.mp4"})
        self.assertEqual((d.size, d.size_approx), (980_000_000, False))        # taille sûre : exacte

    def test_titre_de_page_pour_un_flux_direct(self):
        """master.m3u8 : yt-dlp appelle la vidéo « master ». Le titre de la page vaut mieux."""
        _, calls = self.run_video("https://exemple.fr/hls/master.m3u8", {}, title="Le Jeu de pouvoir")
        self.assertTrue(os.path.basename(calls[0]["opts"]["outtmpl"]).startswith("Le Jeu de pouvoir."),
                        calls[0]["opts"]["outtmpl"])

    def test_titre_de_page_ignore_sur_un_site_connu(self):
        """Sur YouTube, le titre donné par yt-dlp est meilleur que celui de l'onglet."""
        _, calls = self.run_video("https://www.youtube.com/watch?v=abc", {}, title="Titre - YouTube")
        self.assertIn("%(title)", calls[0]["opts"]["outtmpl"])

    def test_nom_choisi_prioritaire_sur_le_titre(self):
        _, calls = self.run_video("https://exemple.fr/master.m3u8", {}, title="Titre de page",
                                  stem="Mon nom")
        self.assertTrue(os.path.basename(calls[0]["opts"]["outtmpl"]).startswith("Mon nom."))


    def test_numerotation_dans_l_ordre_de_demarrage(self):
        """Les (1), (2), (3) doivent suivre l'ordre où les téléchargements ont commencé."""
        FakeYoutubeDL.calls, FakeYoutubeDL.creates = [], True
        FakeYoutubeDL.refuse = staticmethod(lambda opts: None)
        self.addCleanup(setattr, FakeYoutubeDL, "creates", False)
        fake = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {"yt_dlp": fake}):
            taches = [VideoDownload("https://exemple.fr/%d" % i, tmp, stem="Le Jeu de pouvoir")
                      for i in range(3)]
            for t in (taches[2], taches[0], taches[1]):      # démarrées dans le désordre
                t.start()
                t.wait(15)
                self.assertEqual(t.status, "Terminé", t.error or t.status)
            noms = [t.name for t in (taches[2], taches[0], taches[1])]
        self.assertEqual(noms, ["Le Jeu de pouvoir.mp4", "Le Jeu de pouvoir (1).mp4",
                                "Le Jeu de pouvoir (2).mp4"])


    def test_video_terminee_dont_le_fichier_a_bouge(self):
        from pydm.engine import entry_from_task, task_from_entry
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "Film.mp4"), "wb") as f:
                f.write(b"x" * 2048)
            d = VideoDownload("https://vimeo.com/1", tmp, name="Film.mp4")
            d.size = d.done = 2048
            self.assertEqual(d.status, "Terminé")
            e = entry_from_task(d)
            os.remove(os.path.join(tmp, "Film.mp4"))
            t = task_from_entry(e)
            self.assertEqual((t.status, t.size, t.done), ("Terminé", 2048, 2048))
            self.assertTrue(t.missing)


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



class CookiesWindowsTest(unittest.TestCase):
    def test_message_cookies_chrome(self):
        from pydm.engine import friendly_error
        msg = "ERROR: Failed to decrypt with DPAPI. See https://github.com/yt-dlp/yt-dlp/issues/10927"
        self.assertTrue(friendly_error(msg, windows=True).startswith("Chrome chiffre ses cookies sous Windows"))
        self.assertEqual(friendly_error(msg, windows=False), msg)
        self.assertEqual(friendly_error("HTTP Error 404: Not Found", windows=True), "HTTP Error 404: Not Found")

if __name__ == "__main__":
    unittest.main()


def _ytdlp_present():
    import importlib.util
    return importlib.util.find_spec("yt_dlp") is not None


@unittest.skipUnless(shutil.which("ffmpeg") and _ytdlp_present(), "ffmpeg et yt-dlp requis")
class HlsReelTest(unittest.TestCase):
    """Vrai yt-dlp sur un vrai flux HLS : les fragments ne doivent jamais toucher la destination.

    Le réglage `paths` ne suffit pas — yt-dlp l'ignore si le modèle de nom est absolu —, et
    seul un téléchargement réel le montre.
    """

    def servir(self, dossier):
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

        class Muet(SimpleHTTPRequestHandler):
            def __init__(self, *a, **k):
                super().__init__(*a, directory=dossier, **k)

            def log_message(self, *a):
                pass
        srv = ThreadingHTTPServer(("127.0.0.1", 0), Muet)
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return "http://127.0.0.1:%d" % srv.server_address[1]

    def test_fragments_hors_du_dossier_de_destination(self):
        import glob as _glob
        import subprocess as sp
        source = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, source, True)
        cible = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, cible, True)
        sp.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10",
                "-t", "6", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-g", "10",
                "-f", "hls", "-hls_time", "1", "-hls_list_size", "0",
                "-hls_segment_filename", os.path.join(source, "seg%03d.ts"),
                os.path.join(source, "index.m3u8")], check=True, timeout=120)
        base = self.servir(source)

        intrus, temporaire, stop = [], [], threading.Event()

        def guetteur():            # surveille la destination pendant tout le téléchargement
            while not stop.is_set():
                # le .part principal vit tout le téléchargement : signal fiable, contrairement
                # aux fragments qui n'existent que quelques millisecondes
                intrus.extend(os.path.basename(p) for p in _glob.glob(os.path.join(cible, "*"))
                              if ".part" in os.path.basename(p))
                temporaire.append(os.path.isdir(os.path.join(cible, ".pydm-temp")))
                stop.wait(0.02)
        threading.Thread(target=guetteur, daemon=True).start()

        d = VideoDownload(base + "/index.m3u8", cible, parts=3, stem="Essai HLS")
        d.start()
        d.wait(180)
        stop.set()
        self.assertEqual(d.status, "Terminé", d.error or d.status)
        self.assertEqual(sorted(set(intrus)), [],
                         "des fichiers de travail ont été écrits dans le dossier de destination")
        self.assertTrue(any(temporaire), "le dossier .pydm-temp n'a jamais servi")
        restants = os.listdir(cible)
        self.assertEqual(restants, ["Essai HLS.mp4"], restants)
        self.assertGreater(os.path.getsize(os.path.join(cible, "Essai HLS.mp4")), 10_000)
