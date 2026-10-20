import os
import tempfile
import unittest
from unittest import mock

from tests.qt import HAS_QT, app


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class ScheduleDialogTest(unittest.TestCase):
    def setUp(self):
        app()
        from pydm import store
        from pydm.gui import schedule
        self.store, self.schedule = store, schedule

    def test_valeurs_initiales(self):
        s = dict(self.store.DEFAULTS, max_active=4, schedule_on=True, schedule_start="23:00")
        dlg = self.schedule.ScheduleDialog(s)
        self.assertEqual(dlg.max_spin.value(), 4)
        self.assertTrue(dlg.window_box.isChecked())
        self.assertEqual(dlg.start_edit.time().toString("HH:mm"), "23:00")
        self.assertEqual(dlg.end_edit.time().toString("HH:mm"), "07:00")

    def test_resultat(self):
        from PySide6.QtCore import QTime
        s = dict(self.store.DEFAULTS)
        dlg = self.schedule.ScheduleDialog(s)
        dlg.max_spin.setValue(2)
        dlg.speed_box.setChecked(True)
        dlg.speed_spin.setValue(500)
        dlg.end_edit.setTime(QTime(6, 30))
        dlg.action_box.setCurrentText("Éteindre l'ordinateur")
        r = dlg.result_settings()
        self.assertEqual((r["max_active"], r["speed_on"], r["speed_kbps"], r["schedule_end"], r["end_action"]),
                         (2, True, 500, "06:30", "poweroff"))
        self.assertEqual(s["max_active"], 3)          # l'original n'est pas modifié

    def test_compte_a_rebours(self):
        dlg = self.schedule.EndActionDialog("quit", seconds=2)
        fired = []
        dlg.confirmed.connect(lambda: fired.append(1))
        self.assertIn("Quitter PyDM dans 2 s", dlg.label.text())
        dlg.step()
        self.assertIn("1 s", dlg.label.text())
        dlg.step()
        dlg.step()
        self.assertEqual(fired, [1])
        other = self.schedule.EndActionDialog("poweroff", seconds=2)
        other.confirmed.connect(lambda: fired.append(2))
        self.assertIn("Éteindre l'ordinateur dans", other.label.text())
        other.reject()
        other.step()
        other.step()
        self.assertEqual(fired, [1])

    def test_systemctl_echec(self):
        run = self.schedule.run_end_action
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("systemctl")):
            self.assertTrue(run("suspend"))
        with mock.patch("subprocess.run", return_value=mock.Mock(returncode=1, stderr="")):
            self.assertTrue(run("poweroff"))
        with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stderr="")) as m:
            self.assertIsNone(run("suspend"))
        self.assertEqual(m.call_args.args[0], ["systemctl", "suspend"])


@unittest.skipUnless(HAS_QT, "PySide6 absent")
class EndOfQueueTest(unittest.TestCase):
    def setUp(self):
        app()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for name, value in (("CONFIG_DIR", tmp.name), ("SOCKET_PATH", os.path.join(tmp.name, "s"))):
            p = mock.patch(f"pydm.ipc.{name}", value)
            p.start()
            self.addCleanup(p.stop)
        from pydm import store
        from pydm.gui.window import MainWindow
        self.settings = dict(store.DEFAULTS, folder=tmp.name, confirm_add=False)
        self.MainWindow = MainWindow

    def window(self):
        w = self.MainWindow(self.settings)
        w.end_delay = 0
        self.addCleanup(w.deleteLater)
        return w

    def test_fin_de_file_quitter(self):
        self.settings["end_action"] = "quit"
        w = self.window()
        with mock.patch.object(w, "quit_app") as quit_app:
            w.queue_finished()
        quit_app.assert_called_once()

    def test_fin_de_file_rien(self):
        w = self.window()
        with mock.patch.object(w, "quit_app") as quit_app:
            w.queue_finished()
        quit_app.assert_not_called()

    def test_fin_de_file_veille(self):
        self.settings["end_action"] = "suspend"
        w = self.window()
        with mock.patch("pydm.gui.window.run_end_action", return_value=None) as run, \
                mock.patch.object(w, "save_session") as save:
            w.queue_finished()
        run.assert_called_once_with("suspend")
        save.assert_called()

    def test_planification_appliquee(self):
        from pydm.scheduler import LIMITER
        self.addCleanup(setattr, LIMITER, "rate", 0)
        w = self.window()
        new = dict(self.settings, max_active=5, speed_on=True, speed_kbps=100)
        with mock.patch("pydm.gui.window.ScheduleDialog") as Dlg:
            Dlg.return_value.exec.return_value = 1
            Dlg.Accepted = 1
            Dlg.return_value.result_settings.return_value = new
            w.open_schedule()
        self.assertEqual((w.scheduler.max_active, LIMITER.rate), (5, 102400))


if __name__ == "__main__":
    unittest.main()
