# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Réglages (settings.json) et session (session.json) dans le dossier de configuration."""
import json
import os
import tempfile

from . import ipc
from .engine import BROWSERS, QUALITIES
from .scheduler import parse_hhmm


def default_folder():
    fr = os.path.expanduser("~/Téléchargements")
    return fr if os.path.isdir(fr) else os.path.expanduser("~/Downloads")


DEFAULTS = {
    "folder": default_folder(),
    "parts": 8,
    "quality": "Meilleure",
    "browser": "Aucun",
    "clipboard": True,
    "theme": "system",
    "notify": True,
    "close_to_tray": True,
    "autostart": False,
    "tray_hint_shown": False,
    "confirm_add": True,
    "sidebar": True,
    "max_active": 3,
    "speed_on": False,
    "speed_kbps": 2048,
    "schedule_on": False,
    "schedule_start": "01:00",
    "schedule_end": "07:00",
    "end_action": "none",
    "sort_by_type": True,
    "category_dirs": {"video": "Vidéos", "music": "Musique", "document": "Documents", "image": "Images",
                      "archive": "Archives", "program": "Programmes"},
    "window": {},
}
CHOICES = {"theme": ("system", "light", "dark"), "quality": tuple(QUALITIES), "browser": BROWSERS,
           "end_action": ("none", "quit", "suspend", "poweroff")}
RANGES = {"parts": (1, 32), "max_active": (1, 10), "speed_kbps": (16, 1_000_000)}


def _path(name, config_dir):
    return os.path.join(config_dir or ipc.CONFIG_DIR, name)


def _read(path, expected_type):
    """Contenu JSON du fichier, ou None s'il manque. Un fichier illisible est mis de côté en .bak."""
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        data = None
    if not isinstance(data, expected_type):
        try:
            os.replace(path, path + ".bak")
        except OSError:
            pass
        return None
    return data


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        os.chmod(tmp, 0o600)        # la session contient des cookies
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def _valid(key, value):
    default = DEFAULTS[key]
    if type(value) is not type(default):    # bool et int ne se confondent pas
        return False
    if key in RANGES:
        return RANGES[key][0] <= value <= RANGES[key][1]
    if key in ("schedule_start", "schedule_end"):
        return parse_hhmm(value) is not None
    return key not in CHOICES or value in CHOICES[key]


def folder_for(category, settings):
    """Dossier d'un fichier de cette catégorie : sous-dossier du dossier principal, ou chemin absolu."""
    base = os.path.expanduser(settings["folder"])
    defaults = DEFAULTS["category_dirs"]
    if not settings.get("sort_by_type", True) or category not in defaults:
        return base
    sub = (settings.get("category_dirs") or {}).get(category)
    if not isinstance(sub, str) or not sub.strip():
        sub = defaults[category]
    sub = os.path.expanduser(sub.strip())
    return sub if os.path.isabs(sub) else os.path.join(base, sub)


def load_settings(config_dir=None):
    data = _read(_path("settings.json", config_dir), dict) or {}
    return {k: data[k] if k in data and _valid(k, data[k]) else v for k, v in DEFAULTS.items()}


def save_settings(d, config_dir=None):
    _write(_path("settings.json", config_dir), d)


def load_session(config_dir=None):
    return _read(_path("session.json", config_dir), list) or []


def save_session(entries, config_dir=None):
    _write(_path("session.json", config_dir), entries)
