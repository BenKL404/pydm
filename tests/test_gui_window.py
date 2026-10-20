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
        self.want = "now"

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
                 headers=None, filename=None, kind="auto", fmt=None, stem=None, route=None):
        self.calls.append({"url": url, "kind": kind, "quality": quality, "folder": folder, "parts": parts,
                           "fmt": fmt, "stem": stem, "filename": filename, "route": route})
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
        p = mock.patch("pydm.gui.adddialog.fetch_youtube_thumbnail", return_value=None)   # pas de réseau
        p.start()
        self.addCleanup(p.stop)
        self.settings = dict(store.DEFAULTS, folder=self.cfg, confirm_add=False, show_progress=False)
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
        t = FakeDownload("https://a.fr/p.bin", self.cfg)
        t.want = "stop"             # tâche en pause
        self.add_fake(w, t)
        self.select_row(w, 0)
        QTest.keyClick(w.table, Qt.Key_Space)
        w.tick()                    # c'est la file qui démarre la tâche
        self.assertTrue(t.started)
        QTest.keyClick(w.table, Qt.Key_Space)
        self.assertTrue(t.paused)
        self.assertEqual(t.want, "stop")

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

    def notify(self, title, body, folder=None, on_click=None):
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


def entry(url="https://a.fr/x.iso", kind="file", name="x.iso", folder=None, fmt=None, quality="Meilleure",
          auto_folder=False):
    return {"url": url, "kind": kind, "folder": folder, "name": name, "fmt": fmt, "quality": quality,
            "headers": None, "filename": None, "auto_folder": auto_folder}


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class AddFlowTest(WindowCase):
    def window(self, **kw):
        self.settings["confirm_add"] = True
        return super().window(analyzer=lambda *a, **k: {"kind": "error", "error": "test", "drm": False,
                                                         "choices": [], "name": None}, **kw)

    def accept(self, w, entries, start=True, dialog=0):
        w.dialogs[dialog].accepted_tasks.emit(entries, start)
        self.assertTrue(self.tick_until(w, lambda: w.model.rowCount() and
                                        all(isinstance(t, FakeDownload) for t in w.model.tasks())))

    def test_dialogue_ouvert_sans_tache(self):
        w = self.window()
        w.add_urls(["https://a.fr/x.zip"])
        self.assertEqual(len(w.dialogs), 1)
        self.assertEqual(w.model.rowCount(), 0)
        self.assertEqual(self.factory.calls, [])

    def test_telecharger_cree_la_tache(self):
        w = self.window()
        w.add_urls(["https://a.fr/v"])
        self.accept(w, [entry("https://a.fr/v", "video", "Clip.mp4", self.cfg, fmt="137+140")])
        self.assertTrue(w.model.task(0).started)
        self.assertEqual(self.factory.calls[0]["fmt"], "137+140")

    def test_plus_tard_en_file_planifiee(self):
        w = self.window()
        w.add_urls(["https://a.fr/x.iso"])
        self.accept(w, [entry(folder=self.cfg)], start=False)
        w.tick()
        t = w.model.task(0)
        self.assertFalse(t.started)
        self.assertEqual((t.want, t.status), ("later", "En file planifiée"))

    def test_deux_messages_deux_dialogues(self):
        w = self.window()
        w.handle_message({"action": "add", "url": "https://a.fr/1.zip"})
        w.handle_message({"action": "add", "url": "https://a.fr/2.zip"})
        w.tick()
        self.assertEqual(len(w.dialogs), 2)
        self.accept(w, [entry("https://a.fr/2.zip", name="2.zip", folder=self.cfg)], dialog=1)
        self.assertEqual([t.url for t in w.model.tasks()], ["https://a.fr/2.zip"])

    def test_dossier_tilde(self):
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {"HOME": home}):
            w = self.window()
            w.add_urls(["https://a.fr/x.iso"])
            self.accept(w, [entry(folder="~/pydm-test")])
            self.assertEqual(self.factory.calls[0]["folder"], os.path.join(home, "pydm-test"))
            self.assertTrue(os.path.isdir(os.path.join(home, "pydm-test")))

    def test_stem_video(self):
        w = self.window()
        w.add_urls(["https://a.fr/v"])
        self.accept(w, [entry("https://a.fr/v", "video", "Ma vidéo.mp4", self.cfg)])
        self.assertEqual(self.factory.calls[0]["stem"], "Ma vidéo")
        self.assertIsNone(self.factory.calls[0]["filename"])

    def test_nom_de_fichier(self):
        w = self.window()
        w.add_urls(["https://a.fr/x.iso"])
        self.accept(w, [entry(name="renommé.iso", folder=self.cfg)])
        self.assertEqual((self.factory.calls[0]["filename"], self.factory.calls[0]["stem"]), ("renommé.iso", None))


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class AddFlowFixesTest(AddFlowTest):
    def test_meme_nom_rendu_unique(self):
        open(os.path.join(self.cfg, "Ma vidéo.mp4"), "w").close()
        w = self.window()
        w.add_urls(["https://a.fr/v"])
        self.accept(w, [entry("https://a.fr/v", "video", "Ma vidéo.mp4", self.cfg)])
        self.assertEqual(self.factory.calls[0]["stem"], "Ma vidéo (1)")

    def test_fenetre_principale_reste_cachee(self):
        w = self.window()
        w.hide()
        w.handle_message({"action": "add", "url": "https://a.fr/1.zip"})
        w.tick()
        self.assertEqual(len(w.dialogs), 1)
        self.assertFalse(w.isVisible())


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class SortWindowTest(AddFlowTest):
    def test_direct_avec_rangement(self):
        w = WindowCase.window(self)        # confirm_add faux : téléchargement direct
        w.add_urls(["https://a.fr/doc"])
        self.assertTrue(self.tick_until(w, lambda: self.factory.calls))
        route = self.factory.calls[0]["route"]
        self.assertEqual(route("document"), os.path.join(self.cfg, "Documents"))
        self.assertEqual(route("other"), self.cfg)

    def test_direct_sans_rangement(self):
        self.settings["sort_by_type"] = False
        w = WindowCase.window(self)
        w.add_urls(["https://a.fr/doc"])
        self.assertTrue(self.tick_until(w, lambda: self.factory.calls))
        self.assertEqual(self.factory.calls[0]["route"]("document"), self.cfg)

    def test_dialogue_dossier_auto(self):
        w = self.window()
        w.add_urls(["https://a.fr/x"])
        self.accept(w, [entry(folder=self.cfg, auto_folder=True), ])
        self.assertEqual(self.factory.calls[0]["route"]("image"), os.path.join(self.cfg, "Images"))

    def test_dialogue_dossier_choisi(self):
        w = self.window()
        w.add_urls(["https://a.fr/x"])
        self.accept(w, [entry(folder=self.cfg)])
        self.assertIsNone(self.factory.calls[0]["route"])


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class QueueTest(WindowCase):
    def four(self, w):
        w.add_urls([f"https://a.fr/{i}.bin" for i in range(4)])
        self.assertTrue(self.tick_until(w, lambda: w.model.rowCount() == 4 and
                                        all(isinstance(t, FakeDownload) for t in w.model.tasks())))
        w.tick()
        return w.model.tasks()

    def test_quatre_liens_trois_simultanes(self):
        tasks = self.four(self.window())
        self.assertEqual(sum(bool(t.started) for t in tasks), 3)
        self.assertEqual(tasks[3].status, "En file")

    def test_pause_d_une_tache_en_file(self):
        w = self.window()
        tasks = self.four(w)
        w.table.selectRow(3)
        w.pause_selected()
        tasks[0].running, tasks[0].status = False, "Terminé"
        w.tick()
        self.assertFalse(tasks[3].started)
        self.assertEqual(tasks[3].status, "En pause")

    def test_retirer_libere_une_place(self):
        w = self.window()
        tasks = self.four(w)
        w.table.selectRow(0)
        w.remove_selected()
        w.tick()
        self.assertTrue(tasks[3].started)

    def test_redemarrage_dix_entrees(self):
        entries = [{"url": f"http://127.0.0.1:9/{i}.bin", "folder": self.cfg, "parts": 1, "name": None,
                    "headers": {}, "want": "now"} for i in range(10)]
        with open(os.path.join(self.cfg, "session.json"), "w") as f:
            json.dump(entries, f)
        w = self.window()
        w.tick()
        tasks = w.model.tasks()
        try:
            self.assertEqual(sum(t._thread is not None for t in tasks), 3)     # démarrées par la file
            self.assertEqual([t.status for t in tasks[3:]], ["En file"] * 7)
        finally:
            for t in tasks:
                t.pause()

    def test_reglages_appliques(self):
        from pydm.scheduler import LIMITER
        self.addCleanup(setattr, LIMITER, "rate", 0)
        self.settings.update(max_active=1, speed_on=True, speed_kbps=100)
        w = self.window()
        self.assertEqual((w.scheduler.max_active, LIMITER.rate), (1, 102400))


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class QueueCommandsTest(QueueTest):
    def select(self, w, row):
        w.table.clearSelection()
        w.table.selectRow(row)

    def test_forcer(self):
        w = self.window()
        tasks = self.four(w)
        self.select(w, 3)
        w.force_selected()
        w.tick()
        self.assertTrue(tasks[3].started)

    def test_mettre_dans_la_file(self):
        w = self.window()
        t = FakeDownload("https://a.fr/p.bin", self.cfg)
        t.want = "stop"
        w.model.add(t)
        self.select(w, 0)
        w.queue_selected()
        w.tick()
        self.assertEqual((t.want, t.status), ("later", "En file planifiée"))

    def test_monter_retire_le_tri(self):
        from PySide6.QtCore import Qt
        w = self.window()
        for name, size in (("a", 30), ("b", 10), ("c", 20)):
            t = FakeDownload(f"https://a.fr/{name}", self.cfg)
            t.size, t.want = size, "stop"
            w.model.add(t)
        w.proxy.sort(1, Qt.AscendingOrder)       # b, c, a
        self.select(w, 2)                        # a (ligne 0 du modèle)
        w.move_selected(1)
        self.assertEqual([t.url[-1] for t in w.model.tasks()], ["b", "a", "c"])
        self.assertEqual(w.proxy.sortColumn(), -1)
        self.assertEqual([t.url[-1] for t in w.selected_tasks()], ["a"])

    def test_raccourci_ctrl_haut(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        w = self.window()
        for name in "ab":
            t = FakeDownload(f"https://a.fr/{name}", self.cfg)
            t.want = "stop"
            w.model.add(t)
        self.select(w, 1)
        QTest.keyClick(w.table, Qt.Key_Up, Qt.ControlModifier)
        self.assertEqual([t.url[-1] for t in w.model.tasks()], ["b", "a"])
        QTest.keyClick(w.table, Qt.Key_End, Qt.ControlModifier)
        QTest.keyClick(w.table, Qt.Key_Home, Qt.ControlModifier)
        self.assertEqual(w.selected_tasks()[0].url[-1], "b")

    def test_barre_etat_file(self):
        from datetime import datetime
        self.settings.update(max_active=2, schedule_on=True)
        w = self.window()
        w.clock = lambda: datetime(2026, 10, 20, 15, 0)
        w.add_urls([f"https://a.fr/{i}.bin" for i in range(5)])
        self.assertTrue(self.tick_until(w, lambda: all(isinstance(t, FakeDownload) for t in w.model.tasks())
                                        and w.model.rowCount() == 5))
        w.tick()
        self.assertIn("2 en cours · 3 en file · plage 01:00–07:00 (reprise à 01:00)", w.status_left.text())

    def test_bouton_limite(self):
        from pydm import store
        from pydm.scheduler import LIMITER
        self.addCleanup(setattr, LIMITER, "rate", 0)
        w = self.window()
        self.assertEqual(w.limit_btn.text(), "Limite 2.0 Mo/s")
        w.limit_btn.click()
        self.assertIs(w.settings["speed_on"], True)
        self.assertEqual(LIMITER.rate, 2048 * 1024)
        self.assertIs(store.load_settings(self.cfg)["speed_on"], True)
        w.limit_btn.click()
        self.assertEqual(LIMITER.rate, 0)

    def test_menu_planifier(self):
        w = self.window()
        labels = [a.text() for a in w.btn_schedule.menu().actions() if not a.isSeparator()]
        self.assertEqual(labels, ["Démarrer la file", "Arrêter la file", "Planification…"])
        w.btn_schedule.menu().actions()[0].trigger()
        self.assertIs(w.scheduler.queue_started, True)
        self.assertIn("file démarrée", (w.tick() or w.status_left.text()))


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class QueueFixesTest(QueueTest):
    def errored(self, w):
        t = FakeDownload("https://a.fr/e.bin", self.cfg)
        t.error, t.status, t.want = "boom", "Erreur : boom", "stop"
        w.model.add(t)
        w.table.selectRow(0)
        return t

    def test_reessayer_apres_erreur(self):
        w = self.window()
        t = self.errored(w)
        w.resume_selected()
        w.tick()
        self.assertTrue(t.started)
        self.assertIsNone(t.error)

    def test_forcer_apres_erreur(self):
        w = self.window()
        t = self.errored(w)
        w.force_selected()
        self.assertTrue(t.started)

    def test_ligne_analyse_non_demarree(self):
        import threading
        gate = threading.Event()
        self.addCleanup(gate.set)
        slow = Factory()
        original = slow.__call__

        def factory(*a, **k):
            gate.wait(5)
            return original(*a, **k)
        self.factory = factory
        w = self.window()
        w.add_urls(["https://a.fr/lent.bin"])
        placeholder = w.model.task(0)
        w.resume_all()
        w.table.selectRow(0)
        w.force_selected()
        w.tick()
        self.assertIsNone(placeholder._thread)


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class CorrectionsTest(QueueTest):
    def add(self, w, name, want="stop", **kw):
        t = FakeDownload(f"https://a.fr/{name}", self.cfg)
        t.name, t.want = name, want
        for k, v in kw.items():
            setattr(t, k, v)
        w.model.add(t)
        return t

    def test_monter_avec_filtre(self):
        w = self.window()
        for n in ("v1.mp4", "doc.pdf", "v2.mp4"):
            self.add(w, n)
        w.proxy.set_type("video")
        w.table.selectRow(1)                     # v2 (visible n° 2)
        w.move_selected(-1)
        self.assertEqual([t.name for t in w.model.tasks()], ["v2.mp4", "doc.pdf", "v1.mp4"])
        self.assertEqual([t.name for t in w.selected_tasks()], ["v2.mp4"])
        self.assertEqual(w.model.task(w.proxy.mapToSource(w.table.currentIndex()).row()).name, "v2.mp4")

    def test_compte_a_rebours_unique_et_annule(self):
        self.settings["end_action"] = "poweroff"
        w = self.window()
        w.end_delay = 60
        w.queue_finished()
        first = w.end_dialog
        w.queue_finished()
        self.assertIs(w.end_dialog, first)       # pas de seconde fenêtre
        w.add_urls(["https://a.fr/nouveau.bin"])
        self.assertIsNone(w.end_dialog)          # un nouvel ajout annule l'action finale
        self.assertFalse(first.isVisible())

    def test_nom_video(self):
        from pydm.gui.window import video_stem
        self.assertEqual(video_stem("Clip.mp4"), "Clip")
        self.assertEqual(video_stem("Mr. Smith"), "Mr. Smith")
        self.assertEqual(video_stem("Artiste feat. X.mp3"), "Artiste feat. X")
        self.assertIsNone(video_stem(".mp4"))
        self.assertIsNone(video_stem("   "))

    def test_supprimer_apres_la_pause(self):
        from PySide6.QtWidgets import QMessageBox
        w = self.window()
        part = os.path.join(self.cfg, "x.bin.part")
        state = os.path.join(self.cfg, "x.bin.pydm")
        open(part, "w").close()
        t = self.add(w, "x.bin", want="now", running=True)

        def pause():
            t.running = False
            open(state, "w").close()             # l'état est écrit à la pause
        t.pause = pause
        t.files = lambda: [p for p in (part, state) if os.path.exists(p)]
        w.table.selectRow(0)
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            w.delete_selected_files()
        self.assertFalse(os.path.exists(part))
        self.assertFalse(os.path.exists(state))

    def test_extinction_sans_figer(self):
        import time as _time
        from PySide6.QtWidgets import QMessageBox
        self.settings["end_action"] = "suspend"
        w = self.window()
        w.end_delay = 0

        def slow(action):
            _time.sleep(1)
            return "refusé"
        with mock.patch("pydm.gui.window.run_end_action", side_effect=slow), \
                mock.patch.object(QMessageBox, "warning") as warn:
            t0 = _time.time()
            w.queue_finished()
            self.assertLess(_time.time() - t0, 0.5)
            self.assertTrue(self.tick_until(w, lambda: warn.called, 3))

    def test_pause_inactif_si_termine(self):
        w = self.window()
        self.add(w, "fini.bin", want="now", status="Terminé")
        w.table.selectRow(0)
        actions = {a.text(): a for a in w.build_context_menu(w.selected_tasks()).actions()}
        self.assertFalse(actions["Pause"].isEnabled())


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class PrefetchTest(WindowCase):
    URL = "https://www.youtube.com/watch?v=abc"

    def window(self, gate=None):
        from tests.test_cache import FakeAnalyzer
        self.analyzer = FakeAnalyzer(gate=gate)
        return WindowCase.window(self, analyzer=self.analyzer)

    def test_prefetch_sans_fenetre(self):
        self.settings["confirm_add"] = True     # sans fenêtre d'ajout, pas d'analyse anticipée
        w = self.window()
        w.hide()
        w.handle_message({"action": "prefetch", "url": self.URL})
        w.tick()
        self.assertEqual(w.dialogs, [])
        self.assertFalse(w.isVisible())
        self.assertTrue(self.tick_until(w, lambda: w.cache.ready(self.URL)))
        self.assertEqual(len(self.analyzer.calls), 1)

    def test_ajout_apres_prefetch(self):
        self.settings["confirm_add"] = True
        w = self.window()
        w.handle_message({"action": "prefetch", "url": self.URL})
        w.tick()
        self.assertTrue(self.tick_until(w, lambda: w.cache.ready(self.URL)))
        w.add_urls([self.URL + "&list=x"])
        dlg = w.dialogs[0]
        end = time.time() + 2
        while dlg.done_count() < 1 and time.time() < end:
            dlg.poll()
            time.sleep(0.01)
        self.assertEqual(dlg.quality_box.count(), 3)
        self.assertEqual(len(self.analyzer.calls), 1)

    def test_titre_transmis(self):
        import threading
        gate = threading.Event()
        self.addCleanup(gate.set)
        self.settings["confirm_add"] = True
        w = self.window(gate=gate)
        w.handle_message({"action": "add", "url": self.URL, "kind": "video", "title": "Ma vidéo"})
        w.tick()
        self.assertEqual(w.dialogs[0].title_label.text(), "Ma vidéo")


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class PrefetchDirectTest(PrefetchTest):
    def test_pas_de_prefetch_sans_fenetre_d_ajout(self):
        w = self.window()                       # confirm_add faux : le résultat ne servirait pas
        w.handle_message({"action": "prefetch", "url": self.URL})
        w.tick()
        time.sleep(0.2)
        self.assertEqual(self.analyzer.calls, [])


if __name__ == "__main__":
    unittest.main()
