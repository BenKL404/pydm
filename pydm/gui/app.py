# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Démarrage de l'interface Qt : application, thème, fenêtre, liaison avec l'extension."""
import os
import sys

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from .. import integrate
from ..engine import clean_stale_cookie_files
from ..ipc import start_ipc
from . import theme
from .tray import Tray
from .welcome import WelcomeDialog
from .window import MainWindow


def forget_bundle_qt_paths():
    """Programme figé : Qt a lu ses chemins de modules ; on les retire de l'environnement pour que les
    programmes ouverts (gestionnaire de fichiers, lecteur…) utilisent leur propre Qt."""
    if not getattr(sys, "frozen", False):
        return
    QCoreApplication.libraryPaths()         # mémorisés avant le retrait des variables
    for name in ("QT_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        os.environ.pop(name, None)


def integrate_system(window):
    """Depuis l'AppImage : relie PyDM au menu et aux navigateurs (message la première fois)."""
    appimage = integrate.installed_app()
    if not appimage:
        return None
    try:
        status = integrate.integrate(appimage)
    except OSError as e:
        window.statusBar().showMessage(f"Intégration au système impossible : {e}")
        return None
    if status == "new":
        window.welcome = WelcomeDialog(window)
        window.welcome.open()
    return status


def run(settings, default_dir=None, parts=None, minimized=False):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    forget_bundle_qt_paths()
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
    integrate_system(window)
    if not (minimized and window.tray):
        window.show()
    return app.exec()
