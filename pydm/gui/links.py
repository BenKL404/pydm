# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Liens à télécharger trouvés dans un texte collé ou déposé (sans Qt)."""
import urllib.parse

SCHEMES = ("http", "https", "ftp")


def extract_urls(text):
    urls = []
    for line in (text or "").splitlines():
        if line.lstrip().startswith("#"):      # commentaire du format text/uri-list
            continue
        for word in line.split():
            word = word.lstrip("(<\"'").rstrip(".,;)>\"'")
            try:
                u = urllib.parse.urlparse(word)
            except ValueError:
                continue
            if u.scheme.lower() in SCHEMES and u.hostname and word not in urls:
                urls.append(word)
    return urls
