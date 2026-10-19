# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Démarrage de l'interface Qt : application, thème, fenêtre, liaison avec l'extension."""
import sys

from PySide6.QtWidgets import QApplication

from ..ipc import start_ipc
from . import theme
from .window import MainWindow


def run(settings, default_dir=None, parts=None, minimized=False):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("PyDM")
    app.setApplicationDisplayName("PyDM")
    app.setDesktopFileName("pydm")
    app.setWindowIcon(theme.logo())
    theme.apply(app, settings["theme"])
    if default_dir:
        settings["folder"] = default_dir
    if parts:
        settings["parts"] = parts
    window = MainWindow(settings)
    try:
        start_ipc(window.handle_message)
    except OSError as e:
        window.statusBar().showMessage(f"Extension du navigateur indisponible : {e}")
    if not minimized:
        window.show()
    return app.exec()
