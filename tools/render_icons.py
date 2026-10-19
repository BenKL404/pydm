#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Génère les PNG du logo (application et extension) depuis pydm/gui/icons/logo.svg.

Lancement depuis la racine du dépôt :  .venv/bin/python tools/render_icons.py
Puis reconstruire pydm-extension.zip (voir CONTRIBUTING.md).
"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO = os.path.join(ROOT, "pydm", "gui", "icons", "logo.svg")
TARGETS = [(os.path.join(ROOT, "pydm", "gui", "icons", "png", f"pydm-{s}.png"), s)
           for s in (16, 32, 48, 64, 128, 256, 512)]
TARGETS += [(os.path.join(ROOT, "extension", "icons", f"icon{s}.png"), s) for s in (16, 32, 48, 128)]


def main():
    app = QGuiApplication(sys.argv)  # noqa: F841 - requis par QSvgRenderer
    renderer = QSvgRenderer(LOGO)
    if not renderer.isValid():
        sys.exit(f"SVG illisible : {LOGO}")
    for path, size in TARGETS:
        img = QImage(size, size, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        renderer.render(p, QRectF(0, 0, size, size))
        p.end()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not img.save(path, "PNG"):
            sys.exit(f"Écriture impossible : {path}")
        print(f"{size:>4} px → {os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    main()
