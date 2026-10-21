# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Message affiché une fois, quand l'AppImage vient de s'intégrer au système."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from . import theme

RELEASES_URL = "https://github.com/BenKL404/pydm/releases/latest"
CHROME_URL = "https://github.com/BenKL404/pydm/blob/main/LISEZMOI.md#chrome-chromium-brave-edge-vivaldi-opera"


class WelcomeDialog(QMessageBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PyDM")
        self.setIconPixmap(theme.logo().pixmap(64, 64))
        self.setText("<b>PyDM est installé</b>")
        self.setInformativeText("Il est dans le menu des applications, et l'extension du navigateur peut "
                                "maintenant lui envoyer vos téléchargements.")
        self.firefox_btn = self.addButton("Installer l'extension Firefox", QMessageBox.AcceptRole)
        self.chrome_btn = self.addButton("Chrome / Chromium…", QMessageBox.ActionRole)
        self.addButton("Fermer", QMessageBox.RejectRole)
        self.firefox_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(RELEASES_URL)))
        self.chrome_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(CHROME_URL)))

    def text(self):
        return super().text() + "\n" + self.informativeText()
