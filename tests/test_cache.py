import threading
import time
import unittest

from pydm.cache import AnalysisCache, video_key


def choice(label, fmt, ext, height=None, audio=False):
    return dict(label=label, format=fmt, ext=ext, size=height and height * 1000, approx=False,
                height=height, audio_only=audio)


def video_result(**kw):
    r = dict(kind="video", name="Clip.mp4", size=1080000, resumable=True, site="youtube.com", title="Clip",
             duration=10, thumbnail=None, selected=0, ffmpeg_missing=False, error=None, drm=False,
             choices=[choice("1080p", "137+140", "mp4", 1080), choice("720p", "136+140", "mp4", 720),
                      choice("Audio seul · MP3", "ba/b", "mp3", audio=True)])
    r.update(kw)
    return r


class FakeAnalyzer:
    def __init__(self, result=None, gate=None):
        self.calls, self.result, self.gate = [], result, gate
        self.active = self.max_active = 0
        self.lock = threading.Lock()

    def __call__(self, url, headers=None, browser="Aucun", kind="auto", default_quality="Meilleure"):
        with self.lock:
            self.calls.append(url)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        if self.gate:
            self.gate.wait(5)
        with self.lock:
            self.active -= 1
        return dict(self.result or video_result())


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def wait_for(cond, timeout=3):
    end = time.time() + timeout
    while time.time() < end and not cond():
        time.sleep(0.01)
    return cond()


class CacheTest(unittest.TestCase):
    URL = "https://www.youtube.com/watch?v=abc"

    def test_video_key(self):
        self.assertEqual(video_key("https://www.youtube.com/watch?v=abc&list=x&t=3"), "youtube:abc")
        self.assertEqual(video_key("https://youtube.com/shorts/abc"), "youtube:abc")
        self.assertEqual(video_key("https://youtu.be/abc?si=1"), "youtube:abc")
        self.assertEqual(video_key("https://vimeo.com/1#t"), "https://vimeo.com/1")

    def test_prefetch_puis_get(self):
        an = FakeAnalyzer()
        c = AnalysisCache(an)
        c.prefetch(self.URL)
        self.assertTrue(wait_for(lambda: c.ready(self.URL)))
        t = time.time()
        r = c.get(self.URL + "&list=y")
        self.assertLess(time.time() - t, 0.1)
        self.assertEqual((len(an.calls), r["kind"]), (1, "video"))

    def test_get_pendant_prefetch(self):
        gate = threading.Event()
        an = FakeAnalyzer(gate=gate)
        c = AnalysisCache(an)
        c.prefetch(self.URL)
        got = []
        th = threading.Thread(target=lambda: got.append(c.get(self.URL)))
        th.start()
        time.sleep(0.1)
        gate.set()
        th.join(3)
        self.assertEqual((len(an.calls), got[0]["kind"]), (1, "video"))

    def test_expiration(self):
        an, clock = FakeAnalyzer(), Clock()
        c = AnalysisCache(an, clock=clock)
        c.get(self.URL)
        clock.t += 601
        c.get(self.URL)
        self.assertEqual(len(an.calls), 2)

    def test_taille_max(self):
        an = FakeAnalyzer()
        c = AnalysisCache(an, max_items=2)
        for i in range(3):
            c.get(f"https://vimeo.com/{i}")
        c.get("https://vimeo.com/0")
        self.assertEqual(len(an.calls), 4)

    def test_erreur_non_gardee(self):
        an = FakeAnalyzer(result={"kind": "error", "error": "privée", "choices": []})
        c = AnalysisCache(an)
        c.get(self.URL)
        c.get(self.URL)
        self.assertEqual(len(an.calls), 2)

    def test_adaptation(self):
        c = AnalysisCache(FakeAnalyzer())
        c.get(self.URL)
        r = c.get(self.URL, default_quality="720p")
        self.assertEqual((r["selected"], r["name"], r["size"]), (1, "Clip.mp4", 720000))
        r = c.get(self.URL, default_quality="Audio MP3")
        self.assertEqual((r["selected"], r["name"]), (2, "Clip.mp3"))

    def test_deux_simultanees(self):
        gate = threading.Event()
        an = FakeAnalyzer(gate=gate)
        c = AnalysisCache(an, workers=2)
        for i in range(4):          # sous la limite de la file (4 en attente) : aucune n'est abandonnée
            c.prefetch(f"https://vimeo.com/{i}")
        time.sleep(0.2)
        gate.set()
        self.assertTrue(wait_for(lambda: len(an.calls) == 4))
        self.assertEqual(an.max_active, 2)


class SlowAnalyzer(FakeAnalyzer):
    def __call__(self, *a, **k):
        r = super().__call__(*a, **k)
        time.sleep(1.0)
        return r


class SchedulingTest(unittest.TestCase):
    def test_clic_pas_derriere_les_vieilles_analyses(self):
        c = AnalysisCache(SlowAnalyzer())
        for i in range(10):
            c.prefetch(f"https://www.youtube.com/watch?v=vid{i}")
        t = time.time()
        r = c.get("https://www.youtube.com/watch?v=vid9")
        self.assertLess(time.time() - t, 1.6)
        self.assertEqual(r["kind"], "video")

    def test_file_bornee(self):
        an = SlowAnalyzer()
        c = AnalysisCache(an)
        for i in range(10):
            c.prefetch(f"https://vimeo.com/{i}")
        time.sleep(4.5)
        self.assertLessEqual(len(an.calls), 6)          # 2 en cours + 4 en attente au plus
        self.assertTrue(c.ready("https://vimeo.com/9"))  # les plus récentes d'abord


class TwoClicksTest(unittest.TestCase):
    def test_deux_clics_une_analyse(self):
        an = SlowAnalyzer()
        c = AnalysisCache(an)
        url = "https://www.youtube.com/watch?v=z"
        got = []
        threads = [threading.Thread(target=lambda: got.append(c.get(url))) for _ in range(2)]
        for t in threads:
            t.start()
            time.sleep(0.05)
        for t in threads:
            t.join(5)
        self.assertEqual((len(an.calls), len(got)), (1, 2))


if __name__ == "__main__":
    unittest.main()
