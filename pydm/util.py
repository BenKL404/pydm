# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Formatage des tailles et durées, noms de fichiers libres."""
import os


def human(n):
    if n is None:
        return "?"
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if n < 1024:
            return f"{int(n)} {unit}" if unit == "o" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} Po"


def human_time(s):
    if s is None or s < 0:
        return ""
    s = int(s)
    h, rest = divmod(s, 3600)
    m, s = divmod(rest, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


def unique_path(folder, name):
    base, ext = os.path.splitext(name)
    candidate, i = name, 1
    while any(os.path.exists(os.path.join(folder, candidate + suffix))
              for suffix in ("", ".part", ".pydm")):
        candidate = f"{base} ({i}){ext}"
        i += 1
    return candidate
