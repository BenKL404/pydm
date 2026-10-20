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
        self.calls.append({"url": url, "kind": kind, "quality": quality, "folder": folder, "parts": parts})
        return FakeDownload(url, folder, parts)


class WindowCase(unittest.TestCase):
    def setUp(self):
        app()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = tmp.name
        for name, value in (("CONFIG_DIR", self.cfg), ("SOCKET_PATH", os.path.join(self.cfg, "pydm.sock"))):
            patcher = mock.patch(f"pydm.ipc.{name}", value)     # jamais la vraie socket
            patcher.start()
            self.addCleanup(patcher.stop)
        from pydm import store
        from pydm.gui.window import MainWindow
        self.settings = dict(store.DEFAULTS, folder=self.cfg)
        self.factory = Factory()
        self.MainWindow = MainWindow

    def window(self, **kw):
        w = self.MainWindow(self.settings, factory=self.factory, **kw)
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


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class WindowTest(WindowCase):
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

    def test_session_mal_formee(self):
        entries = ["x", None, {"url": None, "folder": self.cfg}, {"url": "https://a.fr/ok.bin"},
                   {"url": "https://a.fr/bon.bin", "folder": self.cfg}]
        with open(os.path.join(self.cfg, "session.json"), "w") as f:
            json.dump(entries, f)
        w = self.window()
        self.assertEqual([t.url for t in w.model.tasks()], ["https://a.fr/bon.bin"])

    def test_options_de_lancement_non_enregistrees(self):
        from pydm import store
        w = self.window(overrides={"folder": "/tmp/ailleurs", "parts": 3})
        w.add_urls(["https://a.fr/o.bin"])
        self.assertTrue(self.tick_until(w, lambda: self.factory.calls))
        self.assertEqual((self.factory.calls[0]["folder"], self.factory.calls[0]["parts"]), ("/tmp/ailleurs", 3))
        w._set("quality", "720p")
        saved = store.load_settings(self.cfg)
        self.assertEqual((saved["folder"], saved["parts"], saved["quality"]), (self.cfg, 8, "720p"))

    def test_raccourcis_uniques(self):
        from PySide6.QtGui import QAction, QShortcut
        w = self.window()
        seqs = [s.key().toString() for s in w.findChildren(QShortcut)]
        seqs += [a.shortcut().toString() for a in w.findChildren(QAction) if not a.shortcut().isEmpty()]
        dupes = sorted({s for s in seqs if seqs.count(s) > 1})
        self.assertEqual(dupes, [])
        self.assertIn("Ctrl+,", seqs)
        self.assertIn("Ctrl+Q", seqs)

    def test_session_enregistree(self):
        w = self.window()
        w.add_urls(["https://a.fr/z.iso"])
        self.assertTrue(self.tick_until(w, lambda: isinstance(w.model.task(0), FakeDownload)))
        w.tick()
        with open(os.path.join(self.cfg, "session.json")) as f:
            self.assertEqual([e["url"] for e in json.load(f)], ["https://a.fr/z.iso"])


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class ComfortTest(WindowCase):
    """Confort : dépôt de liens, collage, barre d'état, suppression, bascule pause/reprise."""

    def add_fake(self, w, task):
        w.model.add(task)
        w.tick()
        return task

    def select_row(self, w, row):
        w.table.selectRow(row)

    def test_depot_de_liens(self):
        from PySide6.QtCore import QMimeData
        w = self.window()
        mime = QMimeData()
        mime.setText("https://a.fr/1\nhttps://a.fr/2\nhttps://a.fr/1")
        w.drop_mime(mime)
        self.assertTrue(self.tick_until(w, lambda: len(self.factory.calls) == 2))
        self.assertEqual(w.model.rowCount(), 2)

    def test_depot_liens_encodes(self):
        from PySide6.QtCore import QMimeData, QUrl
        w = self.window()
        raws = ["http://h.fr/a%20b.zip", "http://h.fr/%C3%A9t%C3%A9.zip"]
        mime = QMimeData()
        mime.setUrls([QUrl(r) for r in raws])
        mime.setText("\n".join(raws))         # les navigateurs fournissent les deux
        w.drop_mime(mime)
        self.assertTrue(self.tick_until(w, lambda: len(self.factory.calls) >= 2))
        self.assertEqual(sorted(c["url"] for c in self.factory.calls), sorted(raws))
        self.assertEqual(w.model.rowCount(), 2)

    def test_coller_ctrl_v(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtTest import QTest
        w = self.window()
        w.settings["clipboard"] = False
        QGuiApplication.clipboard().setText("https://a.fr/z")
        QTest.keyClick(w.table, Qt.Key_V, Qt.ControlModifier)
        self.assertEqual(w.model.rowCount(), 1)

    def test_barre_etat(self):
        w = self.window()
        self.add_fake(w, FakeTask("a", size=10, speed=2 ** 20, running=True, status="Téléchargement"))
        self.add_fake(w, FakeTask("b", size=10, speed=2 * 2 ** 20, running=True, status="Téléchargement"))
        self.add_fake(w, FakeTask("c", size=10, done=10, status="Terminé"))
        w.tick()
        self.assertEqual(w.status_left.text(), "2 en cours · 1 terminé")
        self.assertIn("3.0 Mo/s", w.status_speed.text())

    def test_supprimer_fichier(self):
        from PySide6.QtWidgets import QMessageBox
        w = self.window()
        path = os.path.join(self.cfg, "fichier.bin")
        with open(path, "wb") as f:
            f.write(b"x")
        t = FakeDownload("https://a.fr/fichier.bin", self.cfg)
        t.files = lambda: [path]
        self.add_fake(w, t)
        self.select_row(w, 0)
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            w.delete_selected_files()
        self.assertFalse(os.path.exists(path))
        self.assertEqual(w.model.rowCount(), 0)

    def test_espace_bascule(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        w = self.window()
        t = self.add_fake(w, FakeDownload("https://a.fr/p.bin", self.cfg))
        self.select_row(w, 0)
        QTest.keyClick(w.table, Qt.Key_Space)
        self.assertTrue(t.started)
        QTest.keyClick(w.table, Qt.Key_Space)
        self.assertTrue(t.paused)

    def test_detail(self):
        w = self.window()
        t = FakeDownload("https://a.fr/d.iso", self.cfg)
        t.size, t.done = 4096, 1024
        self.add_fake(w, t)
        self.select_row(w, 0)
        w.tick()
        self.assertIn("https://a.fr/d.iso", w.detail.text())
        w.table.clearSelection()
        w.tick()
        self.assertIn("Aucun téléchargement sélectionné", w.detail.text())


class FakeTray:
    def __init__(self):
        self.messages = []

    def notify(self, title, body, folder=None):
        self.messages.append((title, body))

    def update(self, running, speed):
        pass


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class TrayTest(WindowCase):
    def test_notification_fin(self):
        w = self.window()
        w.tray = FakeTray()
        t = FakeDownload("https://a.fr/fini.iso", self.cfg)
        t.status, t.running = "Téléchargement", True
        w.model.add(t)
        w.tick()
        t.status, t.running = "Terminé", False
        w.tick()
        w.tick()
        self.assertEqual(w.tray.messages, [("Téléchargement terminé", "fini.iso")])

    def test_notification_erreur(self):
        w = self.window()
        w.tray = FakeTray()
        t = FakeDownload("https://a.fr/x.bin", self.cfg)
        w.model.add(t)
        w.tick()
        t.error, t.status = "HTTP Error 403: Forbidden", "Erreur : HTTP Error 403: Forbidden"
        w.tick()
        self.assertEqual(w.tray.messages, [("Échec", "x.bin : HTTP Error 403: Forbidden")])

    def test_pas_de_notification_au_chargement(self):
        w = self.window()
        w.tray = FakeTray()
        t = FakeDownload("https://a.fr/deja.iso", self.cfg)
        t.status = "Terminé"
        w.model.add(t)
        w.tick()
        self.assertEqual(w.tray.messages, [])

    def test_fermer_vers_la_barre(self):
        w = self.window()
        w.tray = FakeTray()
        w.show()
        w.close()
        self.assertFalse(w.isVisible())
        self.assertEqual(len(w.tray.messages), 1)        # avertissement au premier masquage
        self.assertTrue(w.settings["tray_hint_shown"])
        w.show()
        w.close()
        self.assertEqual(len(w.tray.messages), 1)


if __name__ == "__main__":
    unittest.main()
