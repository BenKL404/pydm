import unittest
from datetime import datetime, time

from pydm.scheduler import Scheduler, parse_hhmm

NOW = datetime(2026, 10, 20, 15, 0)


class FakeTask:
    def __init__(self, want="now", running=False, finished=False, error=None):
        self.want, self.running, self._finished, self.error = want, running, finished, error
        self.status, self.started, self.paused = "", 0, 0

    @property
    def finished(self):
        return self._finished

    def start(self):
        self.running = True
        self.started += 1

    def pause(self):
        self.running = False
        self.paused += 1


def at(h, m=0):
    return NOW.replace(hour=h, minute=m)


class SchedulerTest(unittest.TestCase):
    def test_parse_hhmm(self):
        self.assertEqual(parse_hhmm("01:00"), time(1, 0))
        self.assertEqual(parse_hhmm("23:59"), time(23, 59))
        for bad in ("25:00", "1h", "", None, "12:60"):
            self.assertIsNone(parse_hhmm(bad), bad)

    def test_max_active(self):
        tasks = [FakeTask() for _ in range(5)]
        Scheduler(3).tick(tasks, NOW)
        self.assertEqual(sum(t.running for t in tasks), 3)
        self.assertEqual([t.status for t in tasks[3:]], ["En file", "En file"])

    def test_now_avant_later(self):
        tasks = [FakeTask("later"), FakeTask(), FakeTask(), FakeTask()]
        s = Scheduler(3)
        s.start_queue()
        s.tick(tasks, NOW)
        self.assertEqual([t.running for t in tasks], [False, True, True, True])
        self.assertEqual(tasks[0].status, "En file planifiée")

    def test_later_bloque_hors_file(self):
        tasks = [FakeTask("later"), FakeTask("later")]
        s = Scheduler(3)
        s.tick(tasks, NOW)
        self.assertFalse(any(t.running for t in tasks))
        s.start_queue()
        s.tick(tasks, NOW)
        self.assertTrue(all(t.running for t in tasks))

    def test_plage_minuit(self):
        s = Scheduler(3, (time(23, 0), time(7, 0)))
        self.assertTrue(s.queue_active(at(23, 30)))
        self.assertTrue(s.queue_active(at(6, 59)))
        self.assertFalse(s.queue_active(at(7, 0)))
        self.assertFalse(s.queue_active(at(15)))
        t = FakeTask("later")
        s.tick([t], at(15))
        self.assertEqual(t.status, "En file planifiée (reprise à 23:00)")
        self.assertEqual(s.next_start(at(15)), at(23))
        self.assertEqual(s.next_start(at(23, 30)), datetime(2026, 10, 21, 23, 0))

    def test_plage_toute_la_journee(self):
        s = Scheduler(3, (time(8, 0), time(8, 0)))
        self.assertTrue(all(s.queue_active(at(h)) for h in (0, 8, 12, 23)))

    def test_fin_de_plage_met_en_pause(self):
        s = Scheduler(3, (time(1, 0), time(7, 0)))
        t = FakeTask("later")
        s.tick([t], at(6, 59))
        self.assertTrue(t.running)
        s.tick([t], at(7, 1))
        self.assertEqual((t.paused, t.want), (1, "later"))

    def test_stop_queue(self):
        s = Scheduler(3)
        t = FakeTask("later")
        s.start_queue()
        s.tick([t], NOW)
        s.stop_queue()
        s.tick([t], NOW)
        self.assertEqual(t.paused, 1)
        self.assertFalse(s.queue_started)

    def test_force_hors_limite(self):
        tasks = [FakeTask(running=True) for _ in range(3)] + [FakeTask("force")]
        Scheduler(3, (time(1, 0), time(2, 0))).tick(tasks, NOW)
        self.assertTrue(tasks[3].running)

    def test_erreur_sort_de_la_file(self):
        t = FakeTask(error="x")
        Scheduler(3).tick([t], NOW)
        self.assertEqual((t.want, t.started), ("stop", 0))

    def test_baisser_max_active(self):
        tasks = [FakeTask(running=True) for _ in range(5)] + [FakeTask()]
        Scheduler(2).tick(tasks, NOW)
        self.assertEqual(sum(t.paused for t in tasks), 0)
        self.assertFalse(tasks[5].running)
        self.assertEqual(tasks[5].status, "En file")

    def test_signal_de_fin(self):
        s = Scheduler(3)
        s.start_queue()
        t = FakeTask("later")
        self.assertFalse(s.tick([t], NOW))
        t.running, t._finished = False, True
        self.assertTrue(s.tick([t], NOW))
        self.assertFalse(s.tick([t], NOW))
        self.assertFalse(s.queue_started)
        only_now = [FakeTask()]
        s2 = Scheduler(3)
        s2.tick(only_now, NOW)
        only_now[0].running, only_now[0]._finished = False, True
        self.assertFalse(s2.tick(only_now, NOW))


    def test_pause_de_tout_pas_de_fin(self):
        s = Scheduler(3)
        s.start_queue()
        tasks = [FakeTask("later") for _ in range(5)]
        s.tick(tasks, NOW)
        for t in tasks:
            t.want = "stop"
            t.pause()
        self.assertFalse(s.tick(tasks, NOW))


    def test_file_demarree_sans_tache_plus_tard(self):
        s = Scheduler(3)
        s.start_queue()
        s.tick([FakeTask("now")], NOW)
        self.assertFalse(s.queue_started)


if __name__ == "__main__":
    unittest.main()
