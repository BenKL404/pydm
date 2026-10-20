# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Mémoire des analyses : préparer une vidéo avant le clic, réutiliser une analyse récente."""
import os
import re
import threading
import time
import urllib.parse
from collections import OrderedDict

from .analyze import analyze, preselect

QUEUE_MAX = 4      # analyses anticipées en attente au plus
WAIT_MAX = 20      # attente d'une analyse en cours (sous le délai de 30 s de la fenêtre d'ajout)
_YT = re.compile(r"(?:^|\.)(youtube\.com|youtu\.be)$", re.I)


def video_key(url):
    """Clé d'une vidéo : l'identifiant YouTube (playlist et position ignorées), sinon l'URL."""
    u = urllib.parse.urlparse(url)
    host = u.hostname or ""
    if _YT.search(host):
        if host.endswith("youtu.be") and u.path.strip("/"):
            return "youtube:" + u.path.strip("/").split("/")[0]
        m = re.match(r"/(?:shorts|live|embed)/([^/?#]+)", u.path)
        if m:
            return "youtube:" + m.group(1)
        v = urllib.parse.parse_qs(u.query).get("v")
        if v:
            return "youtube:" + v[0]
    return u._replace(fragment="").geturl()


class AnalysisCache:
    def __init__(self, analyzer=analyze, ttl=600, max_items=50, workers=2, clock=time.monotonic):
        self.analyzer, self.ttl, self.max_items, self.clock = analyzer, ttl, max_items, clock
        self._lock = threading.Lock()
        self._items = OrderedDict()             # clé → (heure, résultat)
        self._pending = {}                      # clé → tâche en attente ou en cours
        self._queue = []                        # tâches en attente, de la plus ancienne à la plus récente
        self.workers, self._active = workers, 0

    def _fresh(self, key):
        item = self._items.get(key)
        if item and self.clock() - item[0] <= self.ttl:
            return item[1]
        self._items.pop(key, None)
        return None

    def _store(self, key, result):
        if result.get("kind") in ("video", "file"):     # une erreur sera réessayée au clic
            self._items[key] = (self.clock(), result)
            self._items.move_to_end(key)
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)

    def clear(self):
        """Oublie les analyses (les cookies utilisés ont changé)."""
        with self._lock:
            self._items.clear()

    def ready(self, url):
        with self._lock:
            return self._fresh(video_key(url)) is not None

    def prefetch(self, url, headers=None, browser="Aucun", kind="video"):
        """Analyse en arrière-plan, sauf si elle est déjà faite, en cours ou en attente."""
        key = video_key(url)
        with self._lock:
            if self._fresh(key) is not None or key in self._pending:
                return
            job = {"key": key, "args": (url, headers, browser, kind), "started": False,
                   "done": threading.Event()}
            self._pending[key] = job
            self._queue.append(job)
            while len(self._queue) > QUEUE_MAX:     # pages quittées depuis : on les oublie
                self._drop(self._queue.pop(0))
            if self._active < self.workers:
                self._active += 1
                threading.Thread(target=self._work, daemon=True).start()

    def _drop(self, job):
        self._pending.pop(job["key"], None)
        job["done"].set()

    def _work(self):
        while True:
            with self._lock:
                if not self._queue:
                    self._active -= 1
                    return
                job = self._queue.pop()             # la page ouverte en dernier d'abord
                job["started"] = True
            try:
                result = self.analyzer(*job["args"], "Meilleure")
            except Exception as e:  # noqa: BLE001
                result = {"kind": "error", "error": str(e)}
            with self._lock:
                self._store(job["key"], result)
                if self._pending.get(job["key"]) is job:
                    del self._pending[job["key"]]
            job["done"].set()

    def get(self, url, headers=None, browser="Aucun", kind="auto", default_quality="Meilleure"):
        """Comme analyze() : résultat en mémoire, ou analyse en cours attendue, ou analyse immédiate."""
        key = video_key(url)
        with self._lock:
            result, job = self._fresh(key), self._pending.get(key)
            if result is None and job and not job["started"]:     # en attente : le clic la reprend
                self._queue.remove(job)
                self._drop(job)
                job = None
        if result is None and job:
            job["done"].wait(WAIT_MAX)
            with self._lock:
                result = self._fresh(key)
        if result is None:
            with self._lock:                # un second clic attendra cette analyse
                job = self._pending.get(key)
                if job is None:
                    job = self._pending[key] = {"key": key, "started": True, "done": threading.Event()}
                    mine = True
                else:
                    mine = False
            if not mine:
                job["done"].wait(WAIT_MAX)
                with self._lock:
                    result = self._fresh(key)
            if result is None:
                try:
                    result = self.analyzer(url, headers, browser, kind, default_quality)
                finally:
                    with self._lock:
                        if mine and self._pending.get(key) is job:
                            del self._pending[key]
                    if mine:
                        job["done"].set()
                with self._lock:
                    self._store(key, result)
        return self._adapt(result, default_quality)

    @staticmethod
    def _adapt(result, default_quality):
        """Copie ajustée à la qualité par défaut actuelle (présélection, nom, taille)."""
        r = dict(result)
        if r.get("kind") == "video" and r.get("choices"):
            sel = preselect(r["choices"], default_quality)
            c = r["choices"][sel]
            r.update(selected=sel, size=c["size"],
                     name=f"{os.path.splitext(r.get('name') or 'video')[0]}.{c['ext']}")
        return r
