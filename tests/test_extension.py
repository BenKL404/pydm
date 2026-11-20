import json
import os
import re
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CASES = {
    "https://www.youtube.com/watch?v=abc&list=x": True,
    "https://www.youtube.com/": False,
    "https://www.youtube.com/results?search_query=a": False,
    "https://youtube.com/shorts/xyz": True,
    "https://www.youtube.com/live/xyz": True,
    "https://youtu.be/abc": True,
    "https://vimeo.com/123456": True,
    "https://vimeo.com/channels/staffpicks": False,
    "https://www.dailymotion.com/video/x8abc": True,
    "https://www.reddit.com/r/videos/": False,
    "https://www.reddit.com/r/videos/comments/abc/titre/": True,
    "https://x.com/home": False,
    "https://x.com/user/status/123": True,
    "https://www.instagram.com/someone/": False,
    "https://www.instagram.com/reel/abc/": True,
    "https://www.facebook.com/someone": False,
    "https://www.facebook.com/watch/?v=1": True,
    "https://www.tiktok.com/@user/video/123": True,
    "https://www.tiktok.com/@user": False,
    "https://example.com/video.mp4": False,
}


VIEW = {"width": 1280, "height": 800}
# chaque cas : rectangle de la vidéo, fenêtre, et si la pastille doit s'afficher
PLEINE = {"left": 100, "top": 100, "right": 900, "bottom": 550}
PLACEMENTS = {
    "pleine_page": (PLEINE, True),
    "deborde_a_droite": ({"left": 900, "top": 100, "right": 1500, "bottom": 500}, True),
    "video_etroite": ({"left": 40, "top": 60, "right": 240, "bottom": 200}, True),
    "haut_hors_ecran": ({"left": 100, "top": -300, "right": 900, "bottom": 250}, True),
    "plus_grande_que_l_ecran": ({"left": -200, "top": -200, "right": 1600, "bottom": 1200}, True),
    "bas_de_page": ({"left": 100, "top": 700, "right": 900, "bottom": 1400}, True),
    "sortie_par_le_haut": ({"left": 100, "top": -900, "right": 900, "bottom": -100}, False),
    "sliver_visible": ({"left": 100, "top": 780, "right": 900, "bottom": 1200}, False),
}


@unittest.skipUnless(shutil.which("node"), "node absent")
class PlacementTest(unittest.TestCase):
    """La pastille doit rester dans la vidéo visible *et* dans un coin qui n'est pas déjà pris."""

    def run_js(self, script):
        src = open(os.path.join(ROOT, "extension", "content.js")).read()
        code = re.search(r"^  const WIDTH = .*?^  function near\(.*?^  \}", src, re.M | re.S).group(0)
        out = subprocess.run(["node", "-e", code + "\n" + script], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(re.search(r"const SIZE = (\d+)", src).group(1), "34")
        return json.loads(out.stdout), int(re.search(r"const WIDTH = (\d+)", src).group(1)), 34

    def pick(self, rect, occupes=(), first="null"):
        """Coin retenu quand `occupes` sont couverts par un autre élément."""
        got, width, size = self.run_js("""
          const rect = %s, vue = %s, pris = %s;
          const at = pickCorner(rect, vue, (s) => !pris.includes(s.corner), %s);
          console.log(JSON.stringify(at));
        """ % (json.dumps(rect), json.dumps(VIEW), json.dumps(list(occupes)), first))
        return got, width, size

    def carre(self, at, width, size):
        """Rectangle réellement cliquable de la pastille repliée."""
        left = at["left"] if at["align"] == "flex-start" else at["left"] + width - size
        return [left, at["top"], left + size, at["top"] + size]

    def test_au_dessus_de_la_video_par_defaut(self):
        """Comme IDM : hors de la vidéo, donc hors d'atteinte des commandes du lecteur."""
        at, width, size = self.pick(PLEINE)
        self.assertEqual((at["corner"], at["align"]), ("above", "flex-start"))
        gauche, haut, droite, bas = self.carre(at, width, size)
        self.assertLessEqual(bas, PLEINE["top"], "la pastille mord sur la vidéo")
        self.assertEqual([gauche, droite], [100, 134], "alignée sur le bord gauche de la vidéo")
        self.assertGreaterEqual(haut, 0, "sortie par le haut de la fenêtre")

    def test_sans_place_au_dessus_on_rentre_dans_la_video(self):
        colle_en_haut = {"left": 100, "top": 20, "right": 900, "bottom": 550}
        at, _, _ = self.pick(colle_en_haut)
        self.assertEqual((at["corner"], at["align"]), ("tl", "flex-start"))

    def test_au_dessus_occupe_on_rentre_dans_la_video(self):
        at, _, _ = self.pick(PLEINE, occupes=["above"])
        self.assertEqual((at["corner"], at["align"]), ("tl", "flex-start"))

    def test_coin_occupe_evite(self):
        at, _, _ = self.pick(PLEINE, occupes=["above", "tl"])
        self.assertEqual((at["corner"], at["align"]), ("tr", "flex-end"))

    def test_descend_quand_le_haut_est_pris(self):
        self.assertEqual(self.pick(PLEINE, occupes=["above", "tl", "tr"])[0]["corner"], "bl")
        self.assertEqual(self.pick(PLEINE, occupes=["above", "tl", "tr", "bl"])[0]["corner"], "br")

    def test_tout_occupe_garde_la_place_habituelle(self):
        """Aucune place libre : on affiche quand même, plutôt que de disparaître."""
        at, _, _ = self.pick(PLEINE, occupes=["above", "tl", "tr", "bl", "br"])
        self.assertEqual(at["corner"], "above")

    def test_place_precedente_essayee_en_premier(self):
        """Une place qui marchait est réessayée d'abord : la pastille ne saute pas d'un bord à l'autre."""
        at, _, _ = self.pick(PLEINE, first='"br"')
        self.assertEqual(at["corner"], "br")
        at, _, _ = self.pick(PLEINE, occupes=["br"], first='"br"')
        self.assertEqual(at["corner"], "above")

    def test_garde_affichee_entre_la_video_et_la_pastille(self):
        """Aller cliquer la pastille sort du rectangle de la vidéo : elle ne doit pas s'effacer."""
        got, _, _ = self.run_js("""
          const at = anchor(%s, %s, "above");
          console.log(JSON.stringify({
            dessus: near(at, at.cx, at.cy),
            juste_a_cote: near(at, at.cx + 30, at.cy + 20),
            loin: near(at, at.cx + 300, at.cy),
          }));
        """ % (json.dumps(PLEINE), json.dumps(VIEW)))
        self.assertEqual(got, {"dessus": True, "juste_a_cote": True, "loin": False})

    def test_toujours_en_version_longue(self):
        """Plus de petit rond : le libellé est lisible sans survol."""
        src = open(os.path.join(ROOT, "extension", "content.js")).read()
        self.assertIn('<span class="label">', src)
        self.assertNotIn("max-width: 0", src)
        self.assertNotIn("opacity: 0", src)

    def test_pastille_longue_reste_dans_la_fenetre(self):
        """Vidéo collée au bord droit : la version longue ne doit pas sortir de l'écran."""
        bord = {"left": 1100, "top": 200, "right": 1270, "bottom": 600}
        got, width, _ = self.run_js("""
          console.log(JSON.stringify(anchor(%s, %s, "above")));
        """ % (json.dumps(bord), json.dumps(VIEW)))
        self.assertGreaterEqual(got["left"], 0)
        self.assertLessEqual(got["left"] + width, VIEW["width"])

    def test_toujours_dans_la_video_visible(self):
        for name, (rect, visible) in PLACEMENTS.items():
            for corner in ("tl", "tr", "bl", "br"):
                with self.subTest("%s/%s" % (name, corner)):
                    got, width, size = self.run_js("""
                      console.log(JSON.stringify(anchor(%s, %s, %s)));
                    """ % (json.dumps(rect), json.dumps(VIEW), json.dumps(corner)))
                    if not visible:
                        self.assertIsNone(got)
                        continue
                    a, b, c, d = self.carre(got, width, size)
                    vl, vt = max(rect["left"], 0), max(rect["top"], 0)
                    vr, vb = min(rect["right"], VIEW["width"]), min(rect["bottom"], VIEW["height"])
                    self.assertGreaterEqual(a, vl, "déborde à gauche")
                    self.assertLessEqual(c, vr, "déborde à droite")
                    self.assertGreaterEqual(b, vt, "au-dessus de la vidéo")
                    self.assertLessEqual(d, vb, "sous la vidéo")


@unittest.skipUnless(shutil.which("node"), "node absent")
class RefreshReplyTest(unittest.TestCase):
    """Réponse de l'extension aux demandes de PyDM (pont natif permanent)."""

    def answers(self, script):
        src = open(os.path.join(ROOT, "extension", "background.js")).read()
        code = re.search(r"^async function answerHost\(.*?^\}", src, re.M | re.S).group(0)
        out = subprocess.run(["node", "--input-type=module", "-e", code + "\n" + script],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_reponses(self):
        got = self.answers("""
          const entetes = async (url, referer) => ({ "User-Agent": "Firefox", Referer: referer,
                                                     Cookie: "SID=" + url.length });
          const boum = async () => { throw new Error("cookies refusés"); };
          const cas = {
            demande: await answerHost({ id: "a", action: "refresh", url: "https://a.fr/f",
                                        referer: "https://a.fr/p" }, entetes),
            inconnue: await answerHost({ id: "b", action: "danse" }, entetes),
            sans_id: await answerHost({ action: "refresh", url: "https://a.fr/f" }, entetes),
            pas_un_lien: await answerHost({ id: "d", action: "refresh", url: "javascript:1" }, entetes),
            en_echec: await answerHost({ id: "e", action: "refresh", url: "https://a.fr/f" }, boum),
          };
          console.log(JSON.stringify(cas));
        """)
        self.assertEqual(got["demande"], {"id": "a", "headers": {
            "User-Agent": "Firefox", "Referer": "https://a.fr/p", "Cookie": "SID=14"}})
        self.assertEqual(got["inconnue"], {"id": "b", "error": "unsupported"})
        self.assertIsNone(got["sans_id"])
        self.assertEqual(got["pas_un_lien"], {"id": "d", "error": "bad-url"})
        self.assertEqual(got["en_echec"], {"id": "e", "error": "cookies refusés"})


class BridgeWiringTest(unittest.TestCase):
    """Le pont doit être ouvert au démarrage de l'extension et rouvert s'il tombe."""

    def test_maintien_hors_de_la_video(self):
        """La pastille étant hors de la vidéo, le trajet du curseur ne doit pas l'effacer."""
        src = open(os.path.join(ROOT, "extension", "content.js")).read()
        self.assertIn("near(placed, e.clientX, e.clientY)", src)

    def test_port_persistant(self):
        src = open(os.path.join(ROOT, "extension", "background.js")).read()
        self.assertIn("connectNative(HOST)", src)
        self.assertIn('postMessage({ action: "bridge" })', src)
        self.assertIn("onDisconnect.addListener", src)
        # ouvert à chaque réveil du service worker, pas seulement à l'installation
        self.assertRegex(src, re.compile(r"^connectHost\(\);", re.M))


@unittest.skipUnless(shutil.which("node"), "node absent")
class VideoPageTest(unittest.TestCase):
    def test_pages_video(self):
        src = open(os.path.join(ROOT, "extension", "background.js")).read()
        code = re.search(r"^const VIDEO_PATHS = .*?^function isVideoPage\(url\) \{.*?^\}", src, re.M | re.S).group(0)
        script = f"{code}\nconst cases = {json.dumps(CASES)};\n" \
                 "console.log(JSON.stringify(Object.fromEntries(Object.keys(cases).map(u => [u, isVideoPage(u)]))));"
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        got = json.loads(out.stdout)
        wrong = {u: got[u] for u in CASES if got[u] != CASES[u]}
        self.assertEqual(wrong, {})


if __name__ == "__main__":
    unittest.main()
