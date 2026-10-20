import threading
import unittest

from pydm.scheduler import RateLimiter


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.waits = []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.t += seconds


class RateLimiterTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.evt = threading.Event()

    def limiter(self, rate):
        return RateLimiter(rate, clock=self.clock, sleep=self.clock.sleep)

    def test_debit_respecte(self):
        lim = self.limiter(1_000_000)
        for _ in range(10):
            lim.consume(500_000, self.evt)
        self.assertGreaterEqual(self.clock.t, 4.4)
        self.assertTrue(all(w <= 0.25 for w in self.clock.waits))

    def test_illimite(self):
        lim = self.limiter(0)
        lim.consume(10 ** 9, self.evt)
        self.assertEqual(self.clock.waits, [])

    def test_pause_debloque(self):
        lim = self.limiter(1000)
        self.evt.set()
        lim.consume(10 ** 9, self.evt)
        self.assertEqual(self.clock.waits, [])

    def test_changement_a_chaud(self):
        lim = self.limiter(1000)

        def sleep(seconds):
            self.clock.sleep(seconds)
            lim.rate = 0
        lim.sleep = sleep
        lim.consume(10 ** 6, self.evt)
        self.assertEqual(len(self.clock.waits), 1)


if __name__ == "__main__":
    unittest.main()
