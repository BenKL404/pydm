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
AUTOSTART_FILE = os.path.join(".config", "autostart", "pydm.desktop")
AUTOSTART = """[Desktop Entry]
Type=Application
Name=PyDM
Comment=Gestionnaire de téléchargement multi-connexions
Exec={command} --minimized
Icon=pydm
Terminal=false
X-GNOME-Autostart-enabled=true
"""
ROOT = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.dirname(os.path.abspath(__file__))


def appimage_path():
    """Chemin de l'AppImage en cours d'exécution, ou None hors AppImage."""
    path = os.environ.get("APPIMAGE")
    return path if path and os.path.isfile(path) else None


def launcher(home=None):
    """Commande qui lance PyDM : l'AppImage, sinon le lanceur d'install.sh."""
    return appimage_path() or _install_sh_launcher(home or os.path.expanduser("~"))


_default_launcher = launcher        # set_autostart a un paramètre du même nom


def desktop_quote(path):
    """Chemin protégé pour la ligne Exec= d'un fichier .desktop (mêmes règles qu'install.sh)."""
    return '"' + re.sub(r'(["`$\\])', r"\\\1", path).replace("\\", "\\\\") + '"'


def _extract_mode():
    """AppImage lancée sans FUSE (APPIMAGE_EXTRACT_AND_RUN=1) : les lancements suivants en ont besoin aussi."""
    return os.environ.get("APPIMAGE_EXTRACT_AND_RUN") == "1"


def _install_sh_launcher(home):
    return os.path.join(home, ".local", "bin", "pydm")


def _install_sh_command(home):
    return "Exec=" + desktop_quote(_install_sh_launcher(home))


def set_autostart(enabled, home=None, launcher=None):
    """Démarrage avec la session : l'AppImage (ou `launcher`), sinon le lanceur d'install.sh."""
    home = home or os.path.expanduser("~")
    path = os.path.join(home, AUTOSTART_FILE)
    if enabled:
        command = launcher or _default_launcher(home)
        appimage = command != _install_sh_launcher(home)
        prefix = "env APPIMAGE_EXTRACT_AND_RUN=1 " if appimage and _extract_mode() else ""
        _write(path, AUTOSTART.format(command=prefix + desktop_quote(command)))
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


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
    prefix = "env APPIMAGE_EXTRACT_AND_RUN=1 " if _extract_mode() else ""
    return re.sub(r"^Exec=.*$", lambda m: "Exec=" + prefix + desktop_quote(appimage), text, flags=re.M)


def _update(path, data, mode=0o644):
    """Écrit le fichier seulement si son contenu diffère (la dernière installation lancée gagne)."""
    data = data if isinstance(data, bytes) else data.encode()
    if _read(path) != data:
        _write(path, data, mode)


def integrate(appimage, home=None):
    """Relie PyDM au système. Renvoie "new", "updated" (AppImage déplacée) ou "same"."""
    home = home or os.path.expanduser("~")
    wrapper = os.path.join(home, WRAPPER)
    env = "APPIMAGE_EXTRACT_AND_RUN=1 " if _extract_mode() else ""
    script = f'#!/bin/sh\n{env}exec {shlex.quote(appimage)} --native-host "$@"\n'.encode()
    old = _read(wrapper)
    status = "new" if old is None else ("same" if old == script else "updated")
    _update(wrapper, script, 0o755)
    for folder, key, value in _manifest_dirs(home):
        _update(os.path.join(folder, f"{HOST_NAME}.json"), _manifest(wrapper, key, value))
    _update(os.path.join(home, DESKTOP), _desktop(appimage))
    for size in ICON_SIZES:
        src = os.path.join(PACKAGE, "gui", "icons", "png", f"pydm-{size}.png")
        if os.path.exists(src):
            with open(src, "rb") as f:
                _update(os.path.join(home, ICONS, f"{size}x{size}", "apps", "pydm.png"), f.read())
    autostart = _read(os.path.join(home, AUTOSTART_FILE))
    if autostart is not None and _install_sh_command(home).encode() not in autostart:
        set_autostart(True, home, launcher=appimage)        # démarrage avec la session : suit l'AppImage
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
    install_sh = _install_sh_command(home).encode()
    desktop = os.path.join(home, DESKTOP)
    if install_sh not in (_read(desktop) or install_sh):
        paths.append(desktop)
        paths += [os.path.join(home, ICONS, f"{s}x{s}", "apps", "pydm.png") for s in ICON_SIZES]
    autostart = os.path.join(home, AUTOSTART_FILE)
    if install_sh not in (_read(autostart) or install_sh):
        paths.append(autostart)
    paths.append(wrapper)
    for path in paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
