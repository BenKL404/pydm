# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Panneau de détail du téléchargement sélectionné et mini-courbe de débit."""
import html
from collections import deque

from PySide6.QtCore import QPointF, QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from ..util import human
from . import theme


class DetailPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._task = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        self.label = QLabel()
        self.label.setTextFormat(Qt.RichText)
        self.label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.label.setWordWrap(True)
        self.label.linkActivated.connect(lambda url: QDesktopServices.openUrl(QUrl(url)))
        lay.addWidget(self.label, 1)
        side = QVBoxLayout()
        self.copy = QToolButton()
        self.copy.setText("Copier le lien")
        self.copy.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.copy.clicked.connect(self._copy)
        side.addWidget(self.copy)
        side.addStretch(1)
        lay.addLayout(side)
        self.show_task(None)

    def text(self):
        return self.label.text()

    def _copy(self):
        if self._task:
            QGuiApplication.clipboard().setText(self._task.url)

    def show_task(self, task):
        self._task = task
        self.copy.setEnabled(task is not None)
        if task is None:
            self.label.setText(f"<span style='color:{theme.colors()['muted']}'>Aucun téléchargement sélectionné</span>")
            return
        muted = theme.colors()["muted"]
        folder = html.escape(task.folder)
        rows = [
            ("Lien", html.escape(task.url)),
            ("Dossier", f"<a href='{QUrl.fromLocalFile(task.folder).toString()}'>{folder}</a>"),
            ("Taille", human(task.size)),
            ("Reçu", human(task.done)),
            ("Connexions", f"{task.active_connections} actives / {task.parts} prévues"),
            ("Reprise possible", "oui" if task.resumable else "non"),
        ]
        if task.error:
            rows.append(("Erreur", f"<span style='color:{theme.STATE_COLORS['error']}'>"
                                   f"{html.escape(task.error)}</span>"))
        name = html.escape(task.name or task.url)
        body = "".join(f"<tr><td style='color:{muted};padding-right:14px'>{k}</td><td>{v}</td></tr>"
                       for k, v in rows)
        self.label.setText(f"<b>{name}</b><table style='margin-top:4px'>{body}</table>")


class SpeedSparkline(QWidget):
    """Débit total des 60 dernières secondes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = deque([0.0] * 60, maxlen=60)
        self.setFixedSize(QSize(80, 16))

    def push(self, bytes_per_s):
        self.values.append(max(0.0, float(bytes_per_s)))
        self.update()

    def paintEvent(self, event):
        top = max(self.values) or 1.0
        w, h = self.width() - 2, self.height() - 2
        step = w / (len(self.values) - 1)
        poly = QPolygonF([QPointF(1 + i * step, 1 + h - h * v / top) for i, v in enumerate(self.values)])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(theme.accent(), 1.5))
        p.drawPolyline(poly)
        p.end()
