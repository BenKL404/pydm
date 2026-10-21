# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Intégration de PyDM à Windows : registre de l'utilisateur et manifestes des navigateurs.

Même rôle qu'integrate.py pour l'AppImage : refait à chaque lancement, la dernière installation
lancée gagne. `reg` (le module winreg, ou une imitation pour les tests) et `root` (clé sous
HKEY_CURRENT_USER) sont injectables.
"""
import json
import ntpath
import os
import shutil

HOST_NAME = "com.pydm.host"
FIREFOX_ID = "pydm@local"
CHROME_ID = "feloklndigmnjlmffbddgcdfigpnbcba"
BROWSER_KEYS = (("Mozilla", "firefox.json"), ("Google\\Chrome", "chrome.json"), ("Chromium", "chrome.json"),
                ("Microsoft\\Edge", "chrome.json"))          # Brave, Vivaldi, Opera lisent la clé de Chrome
RUN_KEY = "Microsoft\\Windows\\CurrentVersion\\Run"


def _reg(reg):
    if reg is None:
        import winreg as reg
    return reg


def _hosts_dir(local_appdata):
    return os.path.join(local_appdata, "PyDM", "hosts")


def _host_key(root, browser):
    return f"{root}\\{browser}\\NativeMessagingHosts\\{HOST_NAME}"


def _query(reg, sub):
    try:
        return reg.QueryValue(reg.HKEY_CURRENT_USER, sub)
    except FileNotFoundError:
        return None


def _manifest(host_exe, name):
    key, value = (("allowed_extensions", FIREFOX_ID) if name == "firefox.json"
                  else ("allowed_origins", f"chrome-extension://{CHROME_ID}/"))
    return json.dumps({"name": HOST_NAME, "description": "PyDM - gestionnaire de téléchargement",
                       "path": host_exe, "type": "stdio", key: [value]}, indent=2, ensure_ascii=False)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return
    except OSError:
        pass
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _read_path(manifest):
    try:
        with open(manifest, encoding="utf-8") as f:
            return json.load(f).get("path")
    except (OSError, ValueError):
        return None


def integrate(exe, local_appdata, reg=None, root="Software"):
    """Relie PyDM aux navigateurs. Renvoie "new", "updated" (PyDM déplacé) ou "same"."""
    reg = _reg(reg)
    host_exe = ntpath.join(ntpath.dirname(exe), "pydm-host.exe")
    hosts = _hosts_dir(local_appdata)
    firefox = os.path.join(hosts, "firefox.json")
    if _query(reg, _host_key(root, "Mozilla")) is None:
        status = "new"
    else:
        status = "same" if _read_path(firefox) == host_exe else "updated"
    for name in ("firefox.json", "chrome.json"):
        _write(os.path.join(hosts, name), _manifest(host_exe, name))
    for browser, name in BROWSER_KEYS:
        path = os.path.join(hosts, name)
        if _query(reg, _host_key(root, browser)) != path:
            reg.SetValue(reg.HKEY_CURRENT_USER, _host_key(root, browser), reg.REG_SZ, path)
    if status != "same" and _run_value(reg, root) is not None:
        set_autostart(True, exe, reg, root)        # démarrage avec la session : suit PyDM déplacé
    return status


def _run_value(reg, root):
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, f"{root}\\{RUN_KEY}") as key:
            return reg.QueryValueEx(key, "PyDM")[0]
    except FileNotFoundError:
        return None


def set_autostart(enabled, exe, reg=None, root="Software"):
    """Démarrage avec la session : valeur « PyDM » de la clé Run de l'utilisateur."""
    reg = _reg(reg)
    if enabled:
        with reg.CreateKey(reg.HKEY_CURRENT_USER, f"{root}\\{RUN_KEY}") as key:
            reg.SetValueEx(key, "PyDM", 0, reg.REG_SZ, f'"{exe}" --minimized')
        return
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, f"{root}\\{RUN_KEY}", 0, reg.KEY_SET_VALUE) as key:
            reg.DeleteValue(key, "PyDM")
    except FileNotFoundError:
        pass


def remove(local_appdata, exe, reg=None, root="Software"):
    """Retire les clés qui pointent vers cette installation et la valeur Run ; garde les réglages."""
    reg = _reg(reg)
    hosts = _hosts_dir(local_appdata)
    ours = {os.path.join(hosts, name) for _, name in BROWSER_KEYS}
    for browser, _ in BROWSER_KEYS:
        if _query(reg, _host_key(root, browser)) in ours:
            try:
                reg.DeleteKey(reg.HKEY_CURRENT_USER, _host_key(root, browser))
            except FileNotFoundError:
                pass
    run = _run_value(reg, root)
    if run is not None and run.startswith(f'"{exe}"'):
        set_autostart(False, exe, reg, root)
    shutil.rmtree(hosts, ignore_errors=True)
