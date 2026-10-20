import json
import os
import tempfile
import time
import types
import unittest
from unittest import mock

from tests.qt import HAS_QT, app


def task(**kw):
    t = types.SimpleNamespace(url="https://iso.pop-os.org/pop.iso", name="pop.iso", folder="/tmp", size=1000,
                              speed=2048.0, running=True, finished=False, error=None, status="Téléchargement",
                              want="now", resumable=True, parts=4, active_connections=2,
                              segments=[[0, 499, 500], [500, 999, 120]])
    t.__dict__.update(kw)
    t.done = sum(s[2] for s in t.segments) if t.segments is not None else kw.get("done", 0)
    return t


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class SegmentMapTest(unittest.TestCase):
    def test_segments_a_leur_place(self):
        app()
        from PySide6.QtGui import QColor, QImage
        from pydm.gui import theme
        from pydm.gui.progress import SegmentMap
        m = SegmentMap()
        m.resize(200, 16)
        m.set_segments([[0, 49, 50], [50, 99, 10]], 100)
        img = QImage(200, 16, QImage.Format_ARGB32)
        img.fill(QColor("#000000"))
        m.render(img)
        self.assertEqual(img.pixelColor(50, 8).name(), QColor(theme.STATE_COLORS["done"]).name())  # 1er : fini
        self.assertEqual(img.pixelColor(105, 8).name(), theme.accent().name())                     # 2e : reçu
        self.assertNotIn(img.pixelColor(180, 8).name(), (theme.accent().name(), "#000000"))         # reste


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class ProgressDialogTest(unittest.TestCase):
    def setUp(self):
        app()
        from pydm.gui.progress import ProgressDialog
        self.Dialog = ProgressDialog
        self.window = mock.Mock()

    def dialog(self, t):
        d = self.Dialog(t, self.window)
        self.addCleanup(d.deleteLater)
        d.show()
        d.refresh()
        return d

    def test_textes_et_tableau(self):
        d = self.dialog(task())
        self.assertTrue(d.windowTitle().startswith("62 % · pop.iso"))
        self.assertIn("62 %", d.values["Reçu"].text())
        self.assertEqual(d.values["Reprise"].text(), "possible")
        self.assertEqual(d.table.rowCount(), 2)
        self.assertEqual(d.table.item(0, 3).text(), "terminée")
        self.assertEqual(d.table.item(1, 3).text(), "réception")

    def test_video_sans_segments(self):
        d = self.dialog(task(segments=None, done=300, status="Téléchargement (112/360 fragments)"))
        self.assertTrue(d.map.isHidden())
        self.assertTrue(d.table.isHidden())
        self.assertIn("112/360", d.fragments.text())

    def test_pause_et_reprise(self):
        t = task()
        d = self.dialog(t)
        d.pause_btn.click()
        self.window.pause_task.assert_called_once_with(t)
        t.running, t.want = False, "stop"
        d.refresh()
        self.assertEqual(d.pause_btn.text(), "Reprendre")
        d.pause_btn.click()
        self.window.resume_task.assert_called_once_with(t)

    def test_annuler(self):
        t = task()
        d = self.dialog(t)
        d.cancel_btn.click()
        self.window.pause_task.assert_called_once_with(t)
        self.assertFalse(d.isVisible())

    def test_fin_garde_la_fenetre(self):
        t = task()
        d = self.dialog(t)
        t.running, t.finished, t.status = False, True, "Terminé"
        d.refresh()
        self.assertTrue(d.isVisible())
        self.assertTrue(d.windowTitle().startswith("Terminé"))
        self.assertFalse(d.open_btn.isHidden())

    def test_fermer_a_la_fin(self):
        t = task()
        d = self.dialog(t)
        d.close_box.setChecked(True)
        t.running, t.finished, t.status = False, True, "Terminé"
        d.refresh()
        self.assertFalse(d.isVisible())

    def test_masquer_les_details(self):
        d = self.dialog(task())
        d.details_btn.click()
        self.assertTrue(d.details.isHidden())


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class AutoOpenTest(unittest.TestCase):
    def setUp(self):
        app()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = tmp.name
        for name, value in (("CONFIG_DIR", self.cfg), ("SOCKET_PATH", os.path.join(self.cfg, "s"))):
            p = mock.patch(f"pydm.ipc.{name}", value)
            p.start()
            self.addCleanup(p.stop)
        from pydm import store
        from tests.test_gui_window import Factory
        self.store, self.factory = store, Factory()
        self.settings = dict(store.DEFAULTS, folder=self.cfg, confirm_add=False)

    def window(self):
        from pydm.gui.window import MainWindow
        w = MainWindow(self.settings, factory=self.factory)
        self.addCleanup(w.deleteLater)
        return w

    def until(self, w, cond, timeout=2):
        end = time.time() + timeout
        while time.time() < end and not cond():
            w.tick()
            time.sleep(0.02)
        return cond()

    def test_ouverture_au_demarrage(self):
        w = self.window()
        w.add_urls(["https://a.fr/x.iso"])
        self.assertTrue(self.until(w, lambda: w.progress_windows))
        t = w.model.task(0)
        self.assertIs(w.progress_windows[id(t)].task, t)

    def test_pas_pour_une_reprise_de_session(self):
        with open(os.path.join(self.cfg, "session.json"), "w") as f:
            json.dump([{"url": "http://127.0.0.1:9/r.bin", "folder": self.cfg, "parts": 1, "name": None,
                        "headers": {}, "want": "now"}], f)
        w = self.window()
        w.tick()
        try:
            self.assertEqual(w.progress_windows, {})
        finally:
            for t in w.model.tasks():
                t.pause()

    def test_reglage_desactive(self):
        self.settings["show_progress"] = False
        w = self.window()
        w.add_urls(["https://a.fr/x.iso"])
        self.until(w, lambda: w.model.rowCount() and getattr(w.model.task(0), "started", False))
        w.tick()
        self.assertEqual(w.progress_windows, {})

    def test_double_clic(self):
        self.settings["show_progress"] = False
        w = self.window()
        w.add_urls(["https://a.fr/x.iso"])
        self.assertTrue(self.until(w, lambda: w.model.rowCount() and getattr(w.model.task(0), "started", False)))
        w._double_click(w.proxy.index(0, 0))
        self.assertEqual(len(w.progress_windows), 1)


if __name__ == "__main__":
    unittest.main()
