# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Intégration de l'AppImage au système : menu, icônes et liaison avec les navigateurs.

Refaite à chaque lancement depuis l'AppImage : si le fichier a été déplacé, tout pointe de
nouveau vers lui. Les mêmes manifestes qu'install.sh ; la dernière installation lancée gagne.
"""
import json
import os
import re
import shlex
import sys

HOST_NAME = "com.pydm.host"
FIREFOX_ID = "pydm@local"
CHROME_ID = "feloklndigmnjlmffbddgcdfigpnbcba"
WRAPPER = os.path.join(".local", "share", "pydm", "pydm-host")
DESKTOP = os.path.join(".local", "share", "applications", "pydm.desktop")
ICONS = os.path.join(".local", "share", "icons", "hicolor")
ICON_SIZES = (16, 32, 48, 64, 128, 256, 512)
CHROME_DIRS = ("google-chrome", "google-chrome-beta", "chromium", "BraveSoftware/Brave-Browser",
               "microsoft-edge", "vivaldi", "opera")
ROOT = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.dirname(os.path.abspath(__file__))


def appimage_path():
    """Chemin de l'AppImage en cours d'exécution, ou None hors AppImage."""
    path = os.environ.get("APPIMAGE")
    return path if path and os.path.isfile(path) else None


def launcher(home=None):
    """Commande qui lance PyDM : l'AppImage, sinon le lanceur d'install.sh."""
    return appimage_path() or os.path.join(home or os.path.expanduser("~"), ".local", "bin", "pydm")


def desktop_quote(path):
    """Chemin protégé pour la ligne Exec= d'un fichier .desktop (mêmes règles qu'install.sh)."""
    return '"' + re.sub(r'(["`$\\])', r"\\\1", path).replace("\\", "\\\\") + '"'


def _manifest_dirs(home):
    """(dossier, clé, valeur) de chaque manifeste, comme install.sh."""
    dirs = [(os.path.join(home, ".mozilla", "native-messaging-hosts"), "allowed_extensions", FIREFOX_ID)]
    for d in CHROME_DIRS:
        if d == "google-chrome" or os.path.isdir(os.path.join(home, ".config", d)):
            dirs.append((os.path.join(home, ".config", d, "NativeMessagingHosts"), "allowed_origins",
                         f"chrome-extension://{CHROME_ID}/"))
    return dirs


def _write(path, data, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode())
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def _manifest(path, key, value):
    return json.dumps({"name": HOST_NAME, "description": "PyDM - gestionnaire de téléchargement", "path": path,
                       "type": "stdio", key: [value]}, indent=2)


def _desktop(appimage):
    with open(os.path.join(ROOT, "pydm.desktop")) as f:
        text = f.read()
    return re.sub(r"^Exec=.*$", lambda m: "Exec=" + desktop_quote(appimage), text, flags=re.M)


def integrate(appimage, home=None):
    """Relie PyDM au système. Renvoie "new", "updated" (AppImage déplacée) ou "same"."""
    home = home or os.path.expanduser("~")
    wrapper = os.path.join(home, WRAPPER)
    script = f'#!/bin/sh\nexec {shlex.quote(appimage)} --native-host "$@"\n'.encode()
    old = _read(wrapper)
    status = "new" if old is None else ("same" if old == script else "updated")
    rewrite = status != "same"
    if rewrite:
        _write(wrapper, script, 0o755)
    for folder, key, value in _manifest_dirs(home):
        path = os.path.join(folder, f"{HOST_NAME}.json")
        if rewrite or _read(path) is None:
            _write(path, _manifest(wrapper, key, value))
    desktop = os.path.join(home, DESKTOP)
    if rewrite or _read(desktop) is None:
        _write(desktop, _desktop(appimage))
    for size in ICON_SIZES:
        src = os.path.join(PACKAGE, "gui", "icons", "png", f"pydm-{size}.png")
        dest = os.path.join(home, ICONS, f"{size}x{size}", "apps", "pydm.png")
        if os.path.exists(src) and (rewrite or not os.path.exists(dest)):
            with open(src, "rb") as f:
                _write(dest, f.read())
    return status


def remove(home=None):
    """Retire l'intégration de l'AppImage ; laisse réglages, téléchargements et installation install.sh."""
    home = home or os.path.expanduser("~")
    wrapper = os.path.join(home, WRAPPER)
    paths = []
    for folder, _, _ in _manifest_dirs(home):
        path = os.path.join(folder, f"{HOST_NAME}.json")
        try:
            if json.loads(_read(path) or b"{}").get("path") == wrapper:
                paths.append(path)
        except ValueError:
            pass
    desktop = os.path.join(home, DESKTOP)
    if b".local/bin/pydm" not in (_read(desktop) or b".local/bin/pydm"):
        paths.append(desktop)
        paths += [os.path.join(home, ICONS, f"{s}x{s}", "apps", "pydm.png") for s in ICON_SIZES]
    paths.append(wrapper)
    for path in paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
