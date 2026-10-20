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

_YT = re.compile(r"(?:^|\.)(youtube\.com|youtu\.be)$", re.I)


def video_key(url):
    """Clé d'une vidéo : l'identifiant YouTube (playlist et position ignorées), sinon l'URL."""
    u = urllib.parse.urlparse(url)
    host = u.hostname or ""
    if _YT.search(host):
        if host.endswith("youtu.be") and u.path.strip("/"):
            return "youtube:" + u.path.strip("/").split("/")[0]
        m = re.match(r"/shorts/([^/?#]+)", u.path)
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
        self._pending = {}                      # clé → Event de l'analyse en cours
        self._slots = threading.Semaphore(workers)

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

    def ready(self, url):
        with self._lock:
            return self._fresh(video_key(url)) is not None

    def prefetch(self, url, headers=None, browser="Aucun", kind="video"):
        """Analyse en arrière-plan, sauf si elle est déjà faite ou en cours."""
        key = video_key(url)
        with self._lock:
            if self._fresh(key) is not None or key in self._pending:
                return
            done = self._pending[key] = threading.Event()

        def run():
            with self._slots:
                try:
                    result = self.analyzer(url, headers, browser, kind, "Meilleure")
                except Exception as e:  # noqa: BLE001
                    result = {"kind": "error", "error": str(e)}
            with self._lock:
                self._store(key, result)
                self._pending.pop(key, None)
            done.set()
        threading.Thread(target=run, daemon=True).start()

    def get(self, url, headers=None, browser="Aucun", kind="auto", default_quality="Meilleure"):
        """Comme analyze() : résultat en mémoire, ou attente de l'analyse en cours, ou analyse."""
        key = video_key(url)
        with self._lock:
            result, pending = self._fresh(key), self._pending.get(key)
        if result is None and pending:
            pending.wait(60)
            with self._lock:
                result = self._fresh(key)
        if result is None:
            result = self.analyzer(url, headers, browser, kind, default_quality)
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
