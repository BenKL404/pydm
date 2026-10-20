# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Icône de la barre système : menu, info-bulle et notifications."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..util import human
from . import theme


class Tray:
    def __init__(self, window):
        self.window = window
        self._folder = None
        self._on_click = None
        self.icon = QSystemTrayIcon(theme.logo(), window)
        menu = QMenu(window)
        menu.addAction("Afficher PyDM", window.show_window)
        menu.addSeparator()
        menu.addAction(theme.icon("pause"), "Tout mettre en pause", window.pause_all)
        menu.addAction(theme.icon("resume"), "Tout reprendre", window.resume_all)
        menu.addSeparator()
        menu.addAction("Quitter", window.quit_app)
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._activated)
        self.icon.messageClicked.connect(self._message_clicked)
        self.update(0, 0.0)
        self.icon.show()

    def _activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.window.isVisible() and not self.window.isMinimized():
                self.window.hide()
            else:
                self.window.show_window()

    def _message_clicked(self):
        if self._on_click:
            self._on_click()
        elif self._folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._folder))

    def update(self, running, speed):
        tip = "PyDM"
        if running:
            tip += f" — {running} en cours · ↓ {human(speed)}/s"
        self.icon.setToolTip(tip)

    def notify(self, title, body, folder=None, on_click=None):
        self._folder, self._on_click = folder, on_click
        self.icon.showMessage(title, body, theme.logo(), 6000)
