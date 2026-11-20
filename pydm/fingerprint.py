# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""User-Agent cohérent : celui de la plateforme, épinglé par domaine.

Un serveur qui compare l'en-tête et le cookie refuse une session dont le navigateur change d'une
requête à l'autre : l'UA n'est donc jamais tiré au sort. Celui du navigateur, transmis par
l'extension, est toujours prioritaire — c'est lui qui a obtenu les cookies ; à défaut, PyDM annonce
l'UA correspondant à la plateforme sur laquelle il tourne.
"""
import platform
import threading
import urllib.parse

CHROME = "142.0.0.0"
UA_POOL = {
    "Linux": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/%s Safari/537.36" % CHROME),
    "Windows": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/%s Safari/537.36" % CHROME),
    "Darwin": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/%s Safari/537.36" % CHROME),
}
_PINS = {}                      # hôte → UA retenu pour toute la session
_LOCK = threading.Lock()


def platform_key():
    """Clé de `UA_POOL` pour la machine courante (plateforme inconnue : Linux)."""
    system = platform.system()
    return system if system in UA_POOL else "Linux"


def default_ua():
    """UA annoncé quand le navigateur n'en a pas fourni."""
    return UA_POOL[platform_key()]


def pinned_ua(url, supplied=None):
    """UA à utiliser pour `url` ; `supplied` (celui du navigateur) devient l'UA de l'hôte."""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    with _LOCK:
        if supplied:
            _PINS[host] = supplied
        elif host not in _PINS:
            _PINS[host] = default_ua()
        return _PINS[host]


def reset():
    """Oublie les UA épinglés (tests)."""
    with _LOCK:
        _PINS.clear()
