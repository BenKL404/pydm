# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""File d'attente (téléchargements simultanés, plage horaire) et limite de vitesse globale."""
import re
import threading
import time
from datetime import datetime, timedelta
from datetime import time as dtime

BUCKET_MIN = 64 * 1024


def parse_hhmm(text):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", text or "")
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return dtime(int(m.group(1)), int(m.group(2)))


def _waiting(t):
    return not t.running and not t.finished and not t.error


class Scheduler:
    """Décide quelles tâches tournent ; ne connaît que leurs attributs et l'heure."""

    def __init__(self, max_active=3, window=None):
        self.max_active = max_active
        self.window = window            # None ou (début, fin) en datetime.time
        self.queue_started = False      # file planifiée démarrée à la main
        self.armed = False              # une tâche « later » a été lancée
        self._launched = set()          # tâches lancées par la file planifiée (id)

    def start_queue(self):
        self.queue_started = True

    def stop_queue(self):
        self.queue_started = False

    def in_window(self, now):
        if not self.window:
            return False
        start, end = self.window
        t = now.time()
        if start == end:
            return True
        return start <= t < end if start < end else (t >= start or t < end)

    def queue_active(self, now):
        return self.queue_started or self.in_window(now)

    def next_start(self, now):
        if not self.window:
            return None
        candidate = datetime.combine(now.date(), self.window[0])
        return candidate if candidate > now else candidate + timedelta(days=1)

    def tick(self, tasks, now):
        """Applique les règles ; renvoie True une seule fois quand la file planifiée est terminée."""
        active = self.queue_active(now)
        for t in tasks:
            if not t.running and not t.finished and t.error and t.want != "stop":
                t.want = "stop"
        for t in tasks:
            if t.want == "later" and t.running and not active:
                t.pause()
        for t in tasks:
            if t.want == "force" and _waiting(t):
                t.start()
        free = self.max_active - sum(1 for t in tasks if t.running and t.want in ("now", "later"))
        for want in ("now", "later") if active else ("now",):
            for t in tasks:
                if free <= 0:
                    break
                if t.want == want and _waiting(t):
                    t.start()
                    free -= 1
                    if want == "later":
                        self.armed = True
                        self._launched.add(id(t))
        resume = self.next_start(now) if self.window and not active else None
        for t in tasks:
            if _waiting(t) and t.want == "now":
                t.status = "En file"
            elif _waiting(t) and t.want == "later":
                t.status = "En file planifiée" + (f" (reprise à {resume:%H:%M})" if resume else "")
        pending = any(t.want in ("now", "later") and not t.finished and not t.error for t in tasks)
        forced = any(t.want == "force" and t.running for t in tasks)
        if self.queue_started and not any(t.want == "later" and not t.finished and not t.error for t in tasks):
            self.queue_started = False      # rien dans la file planifiée : rien à « démarrer »
        launched = [t for t in tasks if id(t) in self._launched]
        # une file arrêtée par l'utilisateur (tâches mises en pause) n'est pas « terminée »
        done = bool(launched) and all(t.finished or t.error for t in launched)
        if self.armed and not pending and not forced and done:
            self.armed = False
            self.queue_started = False
            self._launched.clear()
            return True
        return False


class RateLimiter:
    """Seau à jetons partagé par toutes les connexions ; `rate` en octets/s, 0 = illimité."""

    def __init__(self, rate=0, clock=time.monotonic, sleep=None):
        self.rate = rate
        self.clock = clock
        self.sleep = sleep              # attente injectée (tests) ; défaut : stop_evt.wait
        self._lock = threading.Lock()
        self._tokens = 0.0
        self._last = clock()

    def consume(self, n, stop_evt):
        while not stop_evt.is_set():
            with self._lock:
                rate = self.rate
                if rate <= 0:
                    return
                now = self.clock()
                cap = max(rate * 0.5, BUCKET_MIN)
                self._tokens = min(cap, self._tokens + (now - self._last) * rate)
                self._last = now
                if self._tokens >= min(n, cap):     # un bloc plus gros que le seau passe en dette
                    self._tokens -= n
                    return
                wait = (min(n, cap) - self._tokens) / rate
            (self.sleep or stop_evt.wait)(min(wait, 0.25))


LIMITER = RateLimiter()
