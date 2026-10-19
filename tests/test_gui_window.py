import json
import os
import tempfile
import time
import unittest
from unittest import mock

from tests.qt import HAS_QT, app
from tests.test_gui_model import FakeTask


class FakeDownload(FakeTask):
    def __init__(self, url, folder, parts=8, **kw):
        super().__init__(name=os.path.basename(url), url=url)
        self.folder, self.parts, self.headers = folder, parts, {}
        self.kw = kw
        self.started = self.paused = False
        self.active_connections, self.resumable = 0, True

    def start(self):
        self.started, self.running = True, True

    def pause(self):
        self.paused, self.running = True, False

    def wait(self, timeout=None):
        pass

    def files(self):
        return []


class Factory:
    def __init__(self):
        self.calls = []

    def __call__(self, url, folder, parts=8, quality="Meilleure", browser="Aucun",
                 headers=None, filename=None, kind="auto"):
        self.calls.append({"url": url, "kind": kind, "quality": quality})
        return FakeDownload(url, folder, parts)


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class WindowTest(unittest.TestCase):
    def setUp(self):
        app()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = tmp.name
        patcher = mock.patch("pydm.ipc.CONFIG_DIR", self.cfg)
        patcher.start()
        self.addCleanup(patcher.stop)
        from pydm import store
        from pydm.gui.window import MainWindow
        self.settings = dict(store.DEFAULTS, folder=self.cfg)
        self.factory = Factory()
        self.MainWindow = MainWindow

    def window(self):
        w = self.MainWindow(self.settings, factory=self.factory)
        self.addCleanup(w.deleteLater)
        return w

    def tick_until(self, w, cond, timeout=2.0):
        end = time.time() + timeout
        while time.time() < end:
            w.tick()
            if cond():
                return True
            time.sleep(0.02)
        return False

    def test_ajout_lien(self):
        w = self.window()
        w.add_urls(["https://a.fr/x.zip"])
        self.assertEqual(w.model.rowCount(), 1)          # ligne « Analyse… » immédiate
        self.assertTrue(self.tick_until(w, lambda: isinstance(w.model.task(0), FakeDownload)))
        self.assertEqual(w.model.rowCount(), 1)
        self.assertTrue(w.model.task(0).started)

    def test_message_extension(self):
        w = self.window()
        self.assertEqual(w.handle_message({"action": "add", "url": "https://a.fr/y", "kind": "file"}),
                         {"ok": True})
        self.assertTrue(self.tick_until(w, lambda: self.factory.calls))
        self.assertTrue(self.tick_until(w, lambda: isinstance(w.model.task(0), FakeDownload)))
        self.assertEqual(self.factory.calls[0]["kind"], "file")
        self.assertEqual(w.model.rowCount(), 1)

    def test_session_restauree(self):
        entries = [{"url": f"https://a.fr/{n}", "folder": self.cfg, "parts": 4, "name": None, "headers": {}}
                   for n in ("1.bin", "2.bin")]
        with open(os.path.join(self.cfg, "session.json"), "w") as f:
            json.dump(entries, f)
        w = self.window()
        self.assertEqual(w.model.rowCount(), 2)
        self.assertFalse(any(t.running for t in w.model.tasks()))

    def test_session_enregistree(self):
        w = self.window()
        w.add_urls(["https://a.fr/z.iso"])
        self.assertTrue(self.tick_until(w, lambda: isinstance(w.model.task(0), FakeDownload)))
        w.tick()
        with open(os.path.join(self.cfg, "session.json")) as f:
            self.assertEqual([e["url"] for e in json.load(f)], ["https://a.fr/z.iso"])


if __name__ == "__main__":
    unittest.main()
