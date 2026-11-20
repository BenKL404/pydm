#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Serveur d'essai (CI Windows) : ne sert le fichier qu'avec le bon Cookie.

Imprime son adresse sur la sortie standard dès qu'il écoute, puis attend d'être arrêté.
Usage : e2e_cookie_server.py <octets> <cookie>
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from httpserver import serve        # noqa: E402  (chemin ajusté juste au-dessus)


def main(argv):
    size, cookie = int(argv[1]), argv[2]
    url, _stop = serve(os.urandom(size), require_cookie=cookie)
    print(url, flush=True)
    while True:                     # le serveur tourne dans un fil démon
        time.sleep(3600)


if __name__ == "__main__":
    main(sys.argv)
