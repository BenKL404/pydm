import threading
import unittest
import urllib.error
from email.utils import formatdate

from pydm.netpolicy import DomainPolicy, classify, policy_for, reset


def http_error(code, headers=None):
    return urllib.error.HTTPError("https://a.fr/f", code, "", headers or {}, None)


class ClassifyTest(unittest.TestCase):
    def test_refus_de_rythme(self):
        for code in (403, 429, 503, 509):
            self.assertEqual(classify(http_error(code))[:2], (False, True), code)

    def test_refus_definitif(self):
        for code in (401, 402, 404, 410):
            self.assertEqual(classify(http_error(code))[:2], (True, False), code)

    def test_code_inconnu_relance_ordinaire(self):
        self.assertEqual(classify(http_error(500))[:2], (False, False))
        self.assertEqual(classify(urllib.error.URLError("connexion perdue"))[:2], (False, False))
        self.assertEqual(classify(IOError("connexion fermée prématurément"))[:2], (False, False))

    def test_retry_after_entier(self):
        self.assertEqual(classify(http_error(429, {"Retry-After": "30"}))[2], 30.0)

    def test_retry_after_date(self):
        headers = {"Retry-After": formatdate(usegmt=True)}      # maintenant : plus rien à attendre
        self.assertEqual(classify(http_error(503, headers))[2], 0.0)

    def test_retry_after_absent_ou_illisible(self):
        self.assertIsNone(classify(http_error(429))[2])
        self.assertIsNone(classify(http_error(429, {"Retry-After": "bientôt"}))[2])

    def test_retry_after_plafonne(self):
        self.assertEqual(classify(http_error(503, {"Retry-After": "99999"}))[2], 300.0)


class DomainPolicyTest(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.p = DomainPolicy("a.fr", limit=4, clock=lambda: self.now)

    def test_acquire_release_sous_le_plafond(self):
        evt = threading.Event()
        self.assertEqual([self.p.acquire(evt) for _ in range(4)], [True] * 4)
        self.assertEqual(self.p.active, 4)
        self.p.release()
        self.assertEqual(self.p.active, 3)
        self.assertTrue(self.p.acquire(evt))

    def test_acquire_bloque_au_plafond(self):
        evt = threading.Event()
        for _ in range(4):
            self.p.acquire(evt)
        evt.set()                                   # tâche arrêtée pendant l'attente
        self.assertFalse(self.p.acquire(evt))
        self.assertEqual(self.p.active, 4)

    def test_on_reject_divise_et_penalise(self):
        allowed, delay = self.p.on_reject(429, retry_after=5)
        self.assertEqual((allowed, delay), (2, 5.0))        # Retry-After respecté tel quel
        self.assertEqual(self.p.penalty_until, 1005.0)
        self.assertFalse(self.p.floor_hit)
        allowed, delay = self.p.on_reject(403)
        self.assertEqual(allowed, 1)
        self.assertGreater(delay, 0)
        self.assertFalse(self.p.floor_hit)

    def test_floor_hit_quand_refuse_seul(self):
        for _ in range(3):
            self.p.on_reject(403)
        self.assertEqual(self.p.allowed, 1)
        self.assertTrue(self.p.floor_hit)                   # refusé alors qu'une seule connexion est permise

    def test_penalite_bloque_puis_libere(self):
        evt = threading.Event()
        self.p.on_reject(429, retry_after=10)
        self.assertEqual(self.p.penalty_until, 1010.0)
        got = []
        t = threading.Thread(target=lambda: got.append(self.p.acquire(evt)), daemon=True)
        t.start()
        t.join(0.4)
        self.assertTrue(t.is_alive())                       # bloqué tant que la pénalité court
        self.now += 10
        t.join(3)
        self.assertEqual(got, [True])

    def test_on_success_remonte_sans_depasser_le_plafond(self):
        self.p.on_reject(403)
        self.p.on_reject(403)
        self.assertEqual((self.p.allowed, self.p.floor_hit), (1, False))
        self.p.on_success(1024)                             # trop peu : pas de reprise de confiance
        self.assertEqual(self.p.allowed, 1)
        for _ in range(10):
            self.p.on_success(512 * 1024)
        self.assertEqual(self.p.allowed, 4)

    def test_on_success_efface_le_plancher(self):
        for _ in range(3):
            self.p.on_reject(403)
        self.assertTrue(self.p.floor_hit)
        self.p.on_success(4096)
        self.assertFalse(self.p.floor_hit)

    def test_une_politique_par_hote(self):
        reset()
        self.addCleanup(reset)
        a = policy_for("https://a.fr/un", 4)
        self.assertIs(a, policy_for("http://A.FR:8080/deux", 2))
        self.assertIsNot(a, policy_for("https://b.fr/un", 4))
        self.assertEqual(a.max, 4)                          # le plafond le plus large demandé


if __name__ == "__main__":
    unittest.main()
