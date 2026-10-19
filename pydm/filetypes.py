# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Catégorie d'un fichier d'après son extension (icônes, filtres, rangement)."""

CATEGORIES = ("video", "music", "document", "archive", "program", "other")

_EXTENSIONS = {
    "video": "mp4 mkv webm avi mov m4v flv wmv ts m2ts 3gp",
    "music": "mp3 m4a flac ogg opus wav aac wma",
    "document": "pdf doc docx odt rtf txt md epub xls xlsx ods ppt pptx odp csv",
    "archive": "zip rar 7z tar gz tgz bz2 xz zst iso tar.gz tar.xz tar.bz2 tar.zst",
    "program": "deb rpm appimage flatpakref run sh exe msi apk snap",
}
_BY_EXT = {ext: cat for cat, exts in _EXTENSIONS.items() for ext in exts.split()}


def category(name):
    parts = (name or "").lower().rsplit("/", 1)[-1].split(".")
    for n in (2, 1):        # « .tar.xz » avant « .xz »
        if len(parts) > n and ".".join(parts[-n:]) in _BY_EXT:
            return _BY_EXT[".".join(parts[-n:])]
    return "other"
