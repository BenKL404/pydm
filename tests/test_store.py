import json
import os
import stat
import tempfile
import time
import unittest

from pydm import store
from pydm.engine import Download, VideoDownload, entry_from_task, task_from_entry


class SettingsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name

    def write(self, name, text):
        with open(os.path.join(self.dir, name), "w") as f:
            f.write(text)

    def test_defauts_sans_fichier(self):
        self.assertEqual(store.load_settings(self.dir), store.DEFAULTS)

    def test_aller_retour(self):
        s = dict(store.DEFAULTS, parts=4, theme="dark")
        store.save_settings(s, self.dir)
        self.assertEqual(store.load_settings(self.dir), s)
        mode = os.stat(os.path.join(self.dir, "settings.json")).st_mode
        self.assertEqual(stat.S_IMODE(mode), 0o600)

    def test_type_invalide(self):
        self.write("settings.json", json.dumps({"parts": "8", "notify": 1, "theme": "rose"}))
        s = store.load_settings(self.dir)
        self.assertEqual(s["parts"], 8)
        self.assertIs(s["notify"], True)
        self.assertEqual(s["theme"], "system")

    def test_fichier_corrompu(self):
        self.write("settings.json", "{pas du json")
        self.assertEqual(store.load_settings(self.dir), store.DEFAULTS)
        with open(os.path.join(self.dir, "settings.json.bak")) as f:
            self.assertEqual(f.read(), "{pas du json")

    def test_session_corrompue(self):
        self.write("session.json", "[")
        self.assertEqual(store.load_session(self.dir), [])
        self.assertTrue(os.path.exists(os.path.join(self.dir, "session.json.bak")))


class EntryTest(unittest.TestCase):
    def test_session_ancien_format(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        e = {"url": "https://a.fr/x.zip", "folder": tmp.name, "parts": 8, "name": None, "headers": {}}
        t = task_from_entry(e)
        self.assertIsInstance(t, Download)
        self.assertLess(abs(t.added - time.time()), 5)

    def test_entry_aller_retour(self):
        t = VideoDownload("https://v.fr/w", "/tmp", 4, name=None, quality="720p")
        t.added = 1_790_000_000
        t2 = task_from_entry(json.loads(json.dumps(entry_from_task(t))))
        self.assertIsInstance(t2, VideoDownload)
        self.assertEqual((t2.url, t2.quality), (t.url, "720p"))
        self.assertEqual(int(t2.added), 1_790_000_000)


if __name__ == "__main__":
    unittest.main()
