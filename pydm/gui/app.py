# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Démarrage de l'interface Qt : application, thème, fenêtre, liaison avec l'extension."""
import sys

from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from ..engine import clean_stale_cookie_files
from ..ipc import start_ipc
from . import theme
from .tray import Tray
from .window import MainWindow


def run(settings, default_dir=None, parts=None, minimized=False):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("PyDM")
    app.setApplicationDisplayName("PyDM")
    app.setDesktopFileName("pydm")
    app.setWindowIcon(theme.logo())
    theme.apply(app, settings["theme"])
    overrides = {k: v for k, v in (("folder", default_dir), ("parts", parts)) if v}
    window = MainWindow(settings, overrides=overrides)
    app.styleHints().colorSchemeChanged.connect(lambda *_: window.on_color_scheme_changed())
    app.aboutToQuit.connect(window.on_about_to_quit)       # fermeture de session : rien de perdu
    clean_stale_cookie_files()
    if QSystemTrayIcon.isSystemTrayAvailable():
        window.tray = Tray(window)
        app.setQuitOnLastWindowClosed(False)
    try:
        start_ipc(window.handle_message)
    except OSError as e:
        window.statusBar().showMessage(f"Extension du navigateur indisponible : {e}")
    if not (minimized and window.tray):
        window.show()
    return app.exec()
