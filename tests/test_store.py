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
        if os.name != "nt":                         # Windows : droits hérités du dossier de l'utilisateur
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


    def test_reglages_file(self):
        d = store.DEFAULTS
        self.assertEqual((d["max_active"], d["speed_on"], d["speed_kbps"], d["schedule_on"],
                          d["schedule_start"], d["schedule_end"], d["end_action"]),
                         (3, False, 2048, False, "01:00", "07:00", "none"))
        self.write("settings.json", json.dumps({"max_active": 0, "speed_kbps": 5, "schedule_start": "25:00",
                                                "end_action": "reboot", "schedule_end": "23:30"}))
        s = store.load_settings(self.dir)
        self.assertEqual((s["max_active"], s["speed_kbps"], s["schedule_start"], s["end_action"], s["schedule_end"]),
                         (3, 2048, "01:00", "none", "23:30"))

    def test_session_want(self):
        for want, expected in (("now", "now"), ("later", "later"), ("force", "now"), ("stop", "stop")):
            t = Download("https://a.fr/x", "/tmp")
            t.want = want
            self.assertEqual(task_from_entry(json.loads(json.dumps(entry_from_task(t)))).want, expected)
        self.assertEqual(task_from_entry({"url": "https://a.fr/x", "folder": "/tmp"}).want, "stop")


    def test_termine_puis_deplace_pas_retelecharge(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "film.iso")
        open(path, "wb").close()
        t = Download("https://a.fr/film.iso", tmp.name, name="film.iso")
        self.assertTrue(t.finished)
        e = json.loads(json.dumps(entry_from_task(t)))
        os.remove(path)
        self.assertEqual(task_from_entry(e).want, "stop")


class FolderForTest(unittest.TestCase):
    def settings(self, **kw):
        return dict(store.DEFAULTS, folder="/dl", **kw)

    def test_sous_dossiers(self):
        s = self.settings()
        self.assertEqual(store.folder_for("video", s), os.path.normpath(os.path.join("/dl", "Vidéos")))
        self.assertEqual(store.folder_for("image", s), os.path.normpath(os.path.join("/dl", "Images")))
        self.assertEqual(store.folder_for("other", s), os.path.normpath("/dl"))

    def test_rangement_desactive(self):
        self.assertEqual(store.folder_for("video", self.settings(sort_by_type=False)), os.path.normpath("/dl"))

    def test_chemin_absolu_et_tilde(self):
        s = self.settings(category_dirs=dict(store.DEFAULTS["category_dirs"], video="/media/disque/Films",
                                             music="~/Musique"))
        self.assertEqual(store.folder_for("video", s), os.path.normpath("/media/disque/Films"))
        self.assertEqual(store.folder_for("music", s), os.path.normpath(os.path.expanduser("~/Musique")))

    def test_valeur_abimee(self):
        s = self.settings(category_dirs={"video": 3, "music": ""})
        self.assertEqual(store.folder_for("video", s), os.path.normpath(os.path.join("/dl", "Vidéos")))
        self.assertEqual(store.folder_for("music", s), os.path.normpath(os.path.join("/dl", "Musique")))
        self.assertEqual(store.folder_for("document", s), os.path.normpath(os.path.join("/dl", "Documents")))


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


    def test_entry_aller_retour_fmt_stem(self):
        t = VideoDownload("https://v.fr/w", "/tmp", 4, fmt="22", stem="x")
        t2 = task_from_entry(json.loads(json.dumps(entry_from_task(t))))
        self.assertEqual((t2.fmt, t2.stem), ("22", "x"))
        old = task_from_entry({"url": "https://v.fr/w", "folder": "/tmp", "kind": "video"})
        self.assertEqual((old.fmt, old.stem), (None, None))


if __name__ == "__main__":
    unittest.main()
