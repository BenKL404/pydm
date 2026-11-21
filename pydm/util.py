# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Formatage des tailles et durées, noms de fichiers libres et valides."""
import os
import re

RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def limit_text(kbps):
    """« 256 Ko/s », « 2 Mo/s », « 1.5 Mo/s »."""
    if kbps < 1024:
        return f"{kbps} Ko/s"
    return f"{kbps / 1024:.1f}".rstrip("0").rstrip(".") + " Mo/s"


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


NUMBERED = re.compile(r" \((\d+)\)$")       # suffixe de doublon déjà posé sur un nom


def unique_path(folder, name):
    """Nom libre dans le dossier, suffixé « (n) » au besoin.

    Un nom déjà numéroté repart de sa racine : « film (3).mp4 » occupé donne « film (4).mp4 »
    et non « film (3) (1).mp4 ». Un numéro qui fait partie du titre — « Matrix (2) » encore
    libre — est laissé tel quel.
    """
    base, ext = os.path.splitext(name)

    def free(candidate):
        return not any(os.path.exists(os.path.join(folder, candidate + suffix))
                       for suffix in ("", ".part", ".pydm"))
    if free(name):
        return name
    root, i = NUMBERED.sub("", base), 1
    while not free(f"{root} ({i}){ext}"):
        i += 1
    return f"{root} ({i}){ext}"
