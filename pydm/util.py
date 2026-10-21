# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Formatage des tailles et durées, noms de fichiers libres et valides."""
import os
import re

RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def expand_path(path):
    """Chemin saisi par l'utilisateur : « ~ » développé, séparateurs du système (pas de « C:\\x/y »)."""
    return os.path.normpath(os.path.expanduser(path))


def safe_filename(name, windows=(os.name == "nt"), fallback="telechargement"):
    """Nom de fichier valide sur le système : sous Windows, sans caractères interdits ni nom réservé."""
    name = (name or "").strip()
    if windows:
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).rstrip(". ")
        if name.split(".", 1)[0].upper() in RESERVED:
            name = "_" + name
    else:
        name = name.replace("/", "_")
    return name or fallback


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
