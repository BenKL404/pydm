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
PLACEMENTS = {
    "pleine_page": ({"left": 100, "top": 100, "right": 900, "bottom": 550}, True),
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
    """La pastille doit rester dans la partie *visible* de la vidéo, sinon elle est inatteignable."""

    def spots(self):
        src = open(os.path.join(ROOT, "extension", "content.js")).read()
        code = re.search(r"^  const WIDTH = .*?^  function spot\(.*?^  \}", src, re.M | re.S).group(0)
        cases = {name: {"rect": rect, "view": VIEW} for name, (rect, _) in PLACEMENTS.items()}
        script = (code + "\nconst cases = " + json.dumps(cases) + ";\n"
                  "console.log(JSON.stringify(Object.fromEntries("
                  "Object.entries(cases).map(([n, c]) => [n, spot(c.rect, c.view)]))));")
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(re.search(r"const SIZE = (\d+)", src).group(1), "34")
        return json.loads(out.stdout), int(re.search(r"const WIDTH = (\d+)", src).group(1)), 34

    def test_pastille_toujours_dans_la_video_visible(self):
        got, width, size = self.spots()
        for name, (rect, visible) in PLACEMENTS.items():
            with self.subTest(name):
                place = got[name]
                if not visible:
                    self.assertIsNone(place, "rien de cliquable : la pastille doit être cachée")
                    continue
                self.assertIsNotNone(place)
                # la pastille est calée à droite d'un conteneur de `width` : voilà son carré
                right, top = place["left"] + width, place["top"]
                left, bottom = right - size, top + size
                vl, vt = max(rect["left"], 0), max(rect["top"], 0)
                vr, vb = min(rect["right"], VIEW["width"]), min(rect["bottom"], VIEW["height"])
                self.assertGreaterEqual(left, vl, "déborde à gauche de la vidéo visible")
                self.assertLessEqual(right, vr, "déborde à droite de la vidéo visible")
                self.assertGreaterEqual(top, vt, "au-dessus de la vidéo visible")
                self.assertLessEqual(bottom, vb, "sous la vidéo visible")

    def test_calee_en_haut_a_droite(self):
        got, width, size = self.spots()
        plein = got["pleine_page"]
        self.assertEqual((plein["left"] + width, plein["top"]), (890, 110))


@unittest.skipUnless(shutil.which("node"), "node absent")
class ShadowDomTest(unittest.TestCase):
    """Les lecteurs qui encapsulent leur <video> dans un shadow root ouvert doivent être vus."""

    def collect(self, script):
        src = open(os.path.join(ROOT, "extension", "content.js")).read()
        code = re.search(r"^  function collect\(.*?^  \}", src, re.M | re.S).group(0)
        out = subprocess.run(["node", "-e", code + "\n" + script], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_videos_des_shadow_roots_ouverts(self):
        got = self.collect("""
          const node = (vids, hosts = []) => ({
            querySelectorAll: (sel) => (sel === "video" ? vids : hosts),
          });
          const profond = node(["profonde"]);
          const interne = node(["interne"], [{ shadowRoot: profond }]);
          const racine = node(["page"], [{ shadowRoot: interne }, {}, { shadowRoot: node([]) }]);
          console.log(JSON.stringify(collect(racine, [], { left: 1000 })));
        """)
        self.assertEqual(got, ["page", "interne", "profonde"])

    def test_budget_borne_la_recherche(self):
        got = self.collect("""
          const node = (vids, hosts = []) => ({
            querySelectorAll: (sel) => (sel === "video" ? vids : hosts),
          });
          const enfants = Array.from({ length: 50 }, (_, i) => ({ shadowRoot: node(["v" + i]) }));
          console.log(JSON.stringify(collect(node([], enfants), [], { left: 3 })));
        """)
        self.assertEqual(got, ["v0", "v1", "v2"])       # arrêt net, pas de parcours sans fin


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
