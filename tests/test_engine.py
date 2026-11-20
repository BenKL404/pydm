import os
import tempfile
import time
import unittest
from unittest import mock

from pydm import fingerprint, netpolicy
from pydm.engine import Download, collapse_holes, probe
from tests.httpserver import serve


def wait(task, timeout=20):
    end = time.time() + timeout
    while task.running and time.time() < end:
        time.sleep(0.05)


class DownloadTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.data = os.urandom(8 * 1024 * 1024)   # 4 segments : MIN_SPLIT vaut 2 Mo

    def start_server(self, **kw):
        url, stop = serve(self.data, **kw)
        self.addCleanup(stop)
        return url + "/fichier.bin"

    def read(self, d):
        with open(d.path, "rb") as f:
            return f.read()

    def test_download_multi_connexions(self):
        d = Download(self.start_server(), self.dir, parts=4)
        d.start()
        wait(d)
        self.assertEqual(d.status, "Terminé")
        self.assertEqual(self.read(d), self.data)
        self.assertGreaterEqual(len(d.segments), 2)

    def test_pause_puis_reprise(self):
        url = self.start_server(delay=0.02)
        d = Download(url, self.dir, parts=4)
        d.start()
        end = time.time() + 20
        while d.done <= 512 * 1024 and time.time() < end:
            time.sleep(0.02)
        d.pause()
        d.wait()
        self.assertEqual(d.status, "En pause")
        d2 = Download(url, self.dir, 4, name=d.name)
        self.assertEqual(d2.status, "En pause")
        d2.start()
        wait(d2, 60)
        self.assertEqual(d2.status, "Terminé")
        self.assertEqual(self.read(d2), self.data)

    def test_proprietes_detail(self):
        d = Download(self.start_server(), self.dir, parts=4)
        self.assertEqual(d.active_connections, 0)
        d.start()
        wait(d)
        self.assertTrue(d.resumable)
        self.assertEqual(d.active_connections, 0)
        self.assertEqual(d.files(), [d.path])

    def test_meme_nom_en_parallele(self):
        cd = "attachment; filename*=UTF-8''%C3%A9t%C3%A9.bin"
        url = self.start_server(headers={"Content-Disposition": cd}, delay=0.001)
        tasks = [Download(url + f"?id={i}", self.dir, parts=4) for i in range(3)]
        for d in tasks:
            d.start()
        for d in tasks:
            wait(d, 60)
        self.assertEqual(len({d.name for d in tasks}), 3, [d.name for d in tasks])
        for d in tasks:
            self.assertEqual(d.status, "Terminé")
            self.assertEqual(self.read(d), self.data)

    def test_rangement_apres_la_sonde(self):
        cd = "attachment; filename=rapport.pdf"
        url = self.start_server(headers={"Content-Disposition": cd})
        d = Download(url, self.dir, parts=2, route=lambda cat: os.path.join(self.dir, cat))
        d.start()
        wait(d)
        self.assertEqual(d.path, os.path.join(self.dir, "document", "rapport.pdf"))
        self.assertEqual(self.read(d), self.data)

    def test_reprise_dans_le_dossier_d_origine(self):
        url = self.start_server(delay=0.02)
        d = Download(url, self.dir, parts=2, route=lambda cat: os.path.join(self.dir, "range"))
        d.start()
        end = time.time() + 20
        while d.done <= 256 * 1024 and time.time() < end:
            time.sleep(0.02)
        d.pause()
        d.wait()
        folder = d.folder
        d2 = Download(url, folder, 2, name=d.name, route=lambda cat: os.path.join(self.dir, "ailleurs"))
        d2.start()
        wait(d2, 60)
        self.assertEqual(d2.folder, folder)
        self.assertEqual(self.read(d2), self.data)

    def limit(self, rate):
        from pydm.scheduler import LIMITER
        LIMITER.rate = rate
        self.addCleanup(setattr, LIMITER, "rate", 0)
        return LIMITER

    def test_limite_de_vitesse(self):
        data = os.urandom(4 * 1024 * 1024)
        url, stop = serve(data)
        self.addCleanup(stop)
        self.limit(2 * 1024 * 1024)
        d = Download(url + "/l.bin", self.dir, parts=4)
        t = time.time()
        d.start()
        wait(d, 30)
        self.assertGreaterEqual(time.time() - t, 1.5)
        self.assertEqual(self.read(d), data)

    def test_limite_activee_en_cours(self):
        url, stop = serve(os.urandom(16 * 1024 * 1024), delay=0.05)    # ≈ 5 Mo/s sans limite
        self.addCleanup(stop)
        d = Download(url + "/g.bin", self.dir, parts=4)
        self.addCleanup(d.wait, 10)
        self.addCleanup(d.pause)
        d.start()
        end = time.time() + 20
        while d.done <= 1024 * 1024 and time.time() < end:
            time.sleep(0.02)
        self.limit(1024 * 1024)
        time.sleep(0.5)                 # le seau se vide
        before, t0 = d.done, time.time()
        time.sleep(2)
        speed = (d.done - before) / (time.time() - t0)
        self.assertLessEqual(speed, 1.6 * 1024 * 1024)

    def test_serveur_sans_plages(self):
        d = Download(self.start_server(ranges=False), self.dir, parts=4)
        d.start()
        wait(d)
        self.assertIs(d.ranges, False)
        self.assertEqual(d.status, "Terminé")
        self.assertEqual(self.read(d), self.data)

    @unittest.skipIf(os.name == "nt" or getattr(os, "geteuid", lambda: -1)() == 0, "droits POSIX (root ou Windows)")
    def test_dossier_non_inscriptible(self):
        folder = os.path.join(self.dir, "lecture-seule")
        os.mkdir(folder, 0o500)
        self.addCleanup(os.chmod, folder, 0o700)
        d = Download(self.start_server(), folder, parts=4)
        d.start()
        wait(d)
        self.assertTrue(d.status.startswith("Erreur"), d.status)
        self.assertFalse(d.running)

    def test_nom_unicode_content_disposition(self):
        cd = "attachment; filename*=UTF-8''r%C3%A9sum%C3%A9 %C3%A9t%C3%A9.pdf"
        d = Download(self.start_server(headers={"Content-Disposition": cd}), self.dir, parts=2)
        d.start()
        wait(d)
        self.assertEqual(d.name, "résumé été.pdf")



class NameHintTest(unittest.TestCase):
    def test_nom_suggere_nettoye(self):
        from pydm import engine, util
        windows = lambda n, **k: util.safe_filename(n, windows=True, **k)   # noqa: E731
        with mock.patch.object(engine, "safe_filename", side_effect=windows):
            d = engine.Download("https://a.fr/x", tempfile.gettempdir(), name_hint="dossier/a:b*.zip")
        self.assertEqual(d.name_hint, "a_b_.zip")


class TaskLimitTest(unittest.TestCase):
    """Limite de vitesse propre à un téléchargement, en plus de la limite globale."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.data = os.urandom(1024 * 1024)
        url, stop = serve(self.data)
        self.addCleanup(stop)
        self.url = url + "/fichier.bin"

    def test_limite_par_tache(self):
        d = Download(self.url, self.dir, parts=4)
        d.limit_kbps = 256
        self.assertEqual(d.limiter.rate, 256 * 1024)
        t = time.time()
        d.start()
        wait(d)
        self.assertEqual(d.status, "Terminé")
        self.assertGreaterEqual(time.time() - t, 3.0)          # 1 Mo à 256 Ko/s

    def test_limite_changee_en_cours(self):
        d = Download(self.url, self.dir, parts=4)
        d.limit_kbps = 64                                       # 1 Mo prendrait 16 s
        t = time.time()
        d.start()
        time.sleep(0.5)
        d.limit_kbps = 0                                        # levée pendant que les connexions tournent
        wait(d)
        self.assertEqual(d.status, "Terminé")
        self.assertLess(time.time() - t, 5)

    def test_valeurs_invalides(self):
        d = Download(self.url, self.dir)
        self.assertEqual(d.limit_kbps, 0)
        d.limit_kbps = -5
        self.assertEqual((d.limit_kbps, d.limiter.rate), (0, 0))

    def test_session_limite(self):
        from pydm.engine import entry_from_task, task_from_entry
        d = Download(self.url, self.dir)
        self.assertNotIn("limit_kbps", entry_from_task(d))
        d.limit_kbps = 512
        e = entry_from_task(d)
        self.assertEqual(e["limit_kbps"], 512)
        self.assertEqual(task_from_entry(e).limit_kbps, 512)
        for bad in ({}, {"limit_kbps": "x"}, {"limit_kbps": -3}):
            entry = dict(e)
            entry.pop("limit_kbps")
            entry.update(bad)
            self.assertEqual(task_from_entry(entry).limit_kbps, 0)

if __name__ == "__main__":
    unittest.main()


class UserAgentTest(unittest.TestCase):
    """L'UA du navigateur reste prioritaire ; sinon celui de la plateforme, jamais « PyDM »."""

    def setUp(self):
        fingerprint.reset()
        self.addCleanup(fingerprint.reset)
        self.seen = []
        url, stop = serve(b"0123456789", seen=self.seen)
        self.addCleanup(stop)
        self.url = url + "/fichier.bin"

    def test_ua_du_navigateur_prioritaire_puis_epingle(self):
        probe(self.url, {"User-Agent": "NavigateurTest/9", "Referer": "https://exemple.fr/page"})
        probe(self.url)                 # même hôte, lien collé à la main : on garde le même UA
        self.assertEqual([h["User-Agent"] for h in self.seen], ["NavigateurTest/9"] * 2)
        self.assertEqual(self.seen[0]["Referer"], "https://exemple.fr/page")

    def test_ua_par_defaut_sans_navigateur(self):
        probe(self.url)
        self.assertEqual(self.seen[0]["User-Agent"], fingerprint.default_ua())
        self.assertNotIn("PyDM", self.seen[0]["User-Agent"])

    def test_download_utilise_l_ua_du_navigateur(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Download(self.url, tmp, parts=1, headers={"User-Agent": "NavigateurTest/9"})
            d.start()
            wait(d)
        self.assertEqual(d.status, "Terminé", d.status)
        self.assertEqual({h["User-Agent"] for h in self.seen}, {"NavigateurTest/9"})


class CollapseHolesTest(unittest.TestCase):
    """Repli mono-connexion : un segment par trou réel, aucun octet déjà écrit redemandé."""

    @staticmethod
    def holes(segs):
        return [[s[0] + s[2], s[1]] for s in segs if s[1] - (s[0] + s[2]) + 1 > 0]

    def test_deux_trous_non_contigus(self):
        segs = [[0, 99, 50], [100, 199, 100], [200, 299, 30], [300, 399, 100]]
        out = collapse_holes(segs)
        self.assertEqual(self.holes(out), [[50, 99], [230, 299]])
        self.assertEqual(sum(s[2] for s in out), 280)       # aucun octet écrit n'est oublié
        written = [[s[0], s[0] + s[2] - 1] for s in out if s[2]]
        self.assertEqual(written, [[0, 49], [100, 199], [200, 229], [300, 399]])
        self.assertEqual(sorted(written + self.holes(out)),
                         [[0, 49], [50, 99], [100, 199], [200, 229], [230, 299], [300, 399]])

    def test_trous_contigus_fusionnes(self):
        segs = [[0, 99, 100], [100, 199, 40], [200, 299, 0], [300, 399, 0]]
        out = collapse_holes(segs)
        self.assertEqual(self.holes(out), [[140, 399]])
        self.assertEqual(sum(s[2] for s in out), 140)

    def test_segments_en_cours_tronques_sur_place(self):
        """Les connexions encore vivantes doivent finir d'elles-mêmes, sans perdre leur avance."""
        segs = [[0, 99, 50], [100, 199, 0]]
        encours = segs[0]
        out = collapse_holes(segs)
        self.assertIs(out[0], encours)                      # même objet : le worker le voit terminé
        self.assertEqual(encours, [0, 49, 50])
        self.assertEqual(encours[1] - (encours[0] + encours[2]) + 1, 0)

    def test_rien_a_faire(self):
        segs = [[0, 99, 100], [100, 199, 100]]
        self.assertEqual(collapse_holes([list(s) for s in segs]), segs)
        self.assertEqual(collapse_holes([[0, -1, 0]]), [[0, -1, 0]])     # taille inconnue : inchangé


class ServeurRestrictifTest(unittest.TestCase):
    """Refus du parallélisme et du rythme : repli automatique, fichier intact."""

    def setUp(self):
        netpolicy.reset()
        fingerprint.reset()
        self.addCleanup(netpolicy.reset)
        self.addCleanup(fingerprint.reset)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.data = os.urandom(8 * 1024 * 1024)       # 4 segments
        penalty = mock.patch("pydm.netpolicy.BASE_PENALTY", 0.05)
        penalty.start()
        self.addCleanup(penalty.stop)

    def read(self, d):
        with open(d.path, "rb") as f:
            return f.read()

    def test_repli_en_connexion_unique(self):
        url, stop = serve(self.data, max_concurrent=1, delay=0.002)
        self.addCleanup(stop)
        d = Download(url + "/fichier.bin", self.dir, parts=4)
        d.start()
        wait(d, 120)
        self.assertEqual(d.status, "Terminé", d.error or d.status)
        self.assertEqual(self.read(d), self.data)
        self.assertTrue(d._mono, "le repli mono-connexion n'a pas été déclenché")
        self.assertEqual(sum(s[2] for s in d.segments), len(self.data))   # aucun octet en double

    def test_429_avec_retry_after(self):
        url, stop = serve(self.data, throttle_first=2, retry_after=1)
        self.addCleanup(stop)
        d = Download(url + "/fichier.bin", self.dir, parts=4)
        started = time.time()
        d.start()
        wait(d, 120)
        self.assertEqual(d.status, "Terminé", d.error or d.status)
        self.assertEqual(self.read(d), self.data)
        self.assertGreaterEqual(time.time() - started, 1.0)     # Retry-After respecté
        self.assertEqual(netpolicy.policy_for(url).host, "127.0.0.1")

    def test_refus_definitif_sans_relance(self):
        url, stop = serve(self.data, throttle_first=0)
        self.addCleanup(stop)
        seen = []
        url2, stop2 = serve(b"", seen=seen, throttle_first=99, retry_after=None)
        self.addCleanup(stop2)
        d = Download(url2 + "/fichier.bin", self.dir, parts=2)
        d.start()
        wait(d, 60)
        self.assertTrue(d.error, d.status)
        self.assertLessEqual(len(seen), 3)              # trois analyses au plus, pas d'acharnement


class EncodageDesPlagesTest(unittest.TestCase):
    """Une réponse partielle compressée décale tous les offsets : il faut refuser, pas écrire."""

    def setUp(self):
        fingerprint.reset()
        netpolicy.reset()
        self.addCleanup(fingerprint.reset)
        self.addCleanup(netpolicy.reset)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.data = os.urandom(8 * 1024 * 1024)

    def test_identity_impose_sur_les_requetes_de_plage(self):
        seen = []
        url, stop = serve(self.data, seen=seen)
        self.addCleanup(stop)
        probe(url + "/f.bin", {"Accept-Encoding": "gzip, deflate, br"})
        self.assertEqual(seen[0]["Accept-Encoding"], "identity")
        self.assertEqual(seen[0]["Range"], "bytes=0-0")

    def test_reponse_partielle_compressee_refusee(self):
        url, stop = serve(self.data, encoding="gzip")
        self.addCleanup(stop)
        d = Download(url + "/f.bin", self.dir, parts=2)
        d.start()
        wait(d, 60)
        self.assertTrue(d.error, d.status)
        self.assertIn("compress", d.error)
        self.assertFalse(os.path.exists(d.path))        # rien n'est livré
        self.assertEqual(d.status, f"Erreur : {d.error}")
