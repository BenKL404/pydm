# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Fenêtre « Ajouter plusieurs liens » : coller ou taper autant de liens que voulu."""
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout

from . import theme
from .links import extract_urls


class MultiLinksDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajouter plusieurs liens")
        self.setWindowIcon(theme.logo())
        self.resize(560, 360)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Collez ou tapez les liens, un par ligne ou mêlés à du texte :"))
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText("https://exemple.fr/fichier.zip\nhttps://www.youtube.com/watch?v=…")
        self.edit.textChanged.connect(self._count)
        lay.addWidget(self.edit, 1)
        self.count_label = QLabel()
        self.count_label.setStyleSheet(f"color: {theme.colors()['muted']};")
        lay.addWidget(self.count_label)
        buttons = QDialogButtonBox()
        buttons.addButton("Annuler", QDialogButtonBox.RejectRole)
        self.continue_btn = buttons.addButton("Continuer", QDialogButtonBox.AcceptRole)
        self.continue_btn.setObjectName("primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._count()

    def urls(self):
        return extract_urls(self.edit.toPlainText())

    def _count(self):
        n = len(self.urls())
        self.count_label.setText("Aucun lien trouvé" if n == 0 else f"{n} lien{'s' if n > 1 else ''} trouvé"
                                 + ("s" if n > 1 else ""))
        self.continue_btn.setEnabled(n > 0)
