# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Concurrence autorisée par domaine, ajustée sur les refus du serveur.

Un serveur anti-aspiration refuse souvent le *parallélisme* (403/429 dès la deuxième connexion)
plutôt que la requête elle-même. On distingue trois cas : refus définitif (inutile de réessayer),
refus de rythme (on réduit et on attend) et erreur de transport (relance ordinaire). Les
connexions d'un même hôte partagent un plafond qui descend par moitié à chaque refus et remonte
d'une unité par transfert réel — comme un contrôle de congestion.
"""
import random
import threading
import time
import urllib.error
import urllib.parse
from email.utils import parsedate_to_datetime

FATAL = (401, 402, 404, 410, 451)       # le lien ou les droits sont en cause
THROTTLE = (403, 429, 503, 509)         # rythme ou parallélisme refusés
MAX_WAIT = 300.0                        # un Retry-After démesuré ne gèle pas la file
BASE_PENALTY = 2.0                      # attente = BASE_PENALTY × (plafond demandé / plafond restant)
MAX_PENALTY = 30.0
PROGRESS = 256 * 1024                   # transfert jugé réel (regagne une connexion)


def _retry_after(headers):
    """Secondes annoncées par Retry-After (entier ou date HTTP), sinon None."""
    raw = (headers.get("Retry-After") if headers else None) or ""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return min(float(raw), MAX_WAIT)
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if target is None:
        return None
    try:
        left = target.timestamp() - time.time()
    except (OverflowError, OSError, ValueError):
        return None
    return min(max(0.0, left), MAX_WAIT)


def classify(exc):
    """(définitif, rythme, retry_after) pour une exception réseau."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in FATAL, exc.code in THROTTLE, _retry_after(exc.headers)
    return False, False, None


class DomainPolicy:
    """Connexions simultanées permises pour un hôte ; `clock` est injectable (tests)."""

    def __init__(self, host, limit=8, clock=time.monotonic):
        self.host = host
        self.clock = clock
        self.max = max(1, int(limit))
        self.allowed = self.max         # plafond courant, réduit à chaque refus
        self.active = 0
        self.floor_hit = False          # refusé alors qu'une seule connexion était permise
        self.penalty_until = 0.0        # aucune requête avant cet instant
        self._cv = threading.Condition()

    def acquire(self, stop_evt):
        """Attend une place ; False si la tâche est arrêtée pendant l'attente."""
        with self._cv:
            while not stop_evt.is_set():
                left = self.penalty_until - self.clock()
                if left <= 0 and self.active < self.allowed:
                    self.active += 1
                    return True
                self._cv.wait(max(0.05, min(left if left > 0 else 0.5, 1.0)))
            return False

    def release(self):
        with self._cv:
            self.active = max(0, self.active - 1)
            self._cv.notify()

    def on_success(self, read):
        """Un transfert a abouti : le plancher est validé, et la confiance remonte d'un cran."""
        if read <= 0:
            return
        with self._cv:
            self.floor_hit = False
            if read >= PROGRESS and self.allowed < self.max:
                self.allowed += 1
                self._cv.notify()

    def on_reject(self, code, retry_after=None):
        """Refus de rythme : renvoie (plafond, attente). Retry-After est respecté tel quel."""
        with self._cv:
            if self.allowed <= 1:
                self.floor_hit = True
            self.allowed = max(1, self.allowed // 2)
            if retry_after is None:
                delay = min(MAX_PENALTY, BASE_PENALTY * (self.max / float(self.allowed)))
                delay *= 0.75 + random.random() * 0.5       # jitter : pas de réveil en troupeau
            else:
                delay = float(retry_after)
            self.penalty_until = max(self.penalty_until, self.clock() + delay)
            self._cv.notify_all()
            return self.allowed, delay


_POLICIES = {}
_LOCK = threading.Lock()


def policy_for(url, limit=8):
    """Politique partagée par toutes les connexions de l'hôte de `url`."""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    with _LOCK:
        p = _POLICIES.get(host)
        if p is None:
            p = _POLICIES[host] = DomainPolicy(host, limit)
        else:
            p.max = max(p.max, max(1, int(limit)))
        return p


def reset():
    """Oublie les politiques (tests)."""
    with _LOCK:
        _POLICIES.clear()
