# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Panneau de détail du téléchargement sélectionné, mini-courbe de débit, textes longs."""
import html
import re
from collections import deque

from PySide6.QtCore import QPointF, QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPainter, QPen, QPolygonF, QTextLayout, QTextOption
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from ..util import human
from . import theme


ZWSP = "\u200b"


def breakable(text, run=30, chunk=24):
    """Texte où les longues suites sans espace (URL, noms) peuvent passer à la ligne : un QLabel ne
    coupe qu'aux espaces, et sinon impose leur largeur à toute la fenêtre. Coupures invisibles."""
    def cut(m):
        parts = [p for p in re.split(r"(?<=[/?&=,._\-])", m.group(0)) if p]
        return ZWSP.join(ZWSP.join(p[i:i + chunk] for i in range(0, len(p), chunk)) for p in parts)
    return re.sub(r"\S{%d,}" % run, cut, text or "")


class ElidedLabel(QLabel):
    """Texte sur `max_lines` lignes au plus, « … » à la fin, texte complet en infobulle."""

    def __init__(self, text="", max_lines=2, parent=None):
        super().__init__(parent)
        self.max_lines = max_lines
        self._full = ""
        self.setTextFormat(Qt.PlainText)       # un titre « <b>…</b> » s'affiche tel quel
        self.setText(text)

    def full_text(self):
        return self._full

    def setText(self, text):
        self._full = text or ""
        self.setToolTip(self._full)
        self._show(self.width())
        self.updateGeometry()

    def _lines(self, width):
        width = max(width, 40)
        text = breakable(self._full)
        layout = QTextLayout(text, self.font())
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option)
        spans = []
        layout.beginLayout()
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            spans.append((line.textStart(), line.textLength()))
        layout.endLayout()
        units = text.encode("utf-16-le")       # QTextLayout compte en UTF-16 (un émoji = 2 unités)

        def part(start, length=None):
            end = len(units) if length is None else 2 * (start + length)
            return units[2 * start:end].decode("utf-16-le", errors="ignore").replace(ZWSP, "")
        lines = [part(s, n).strip() for s, n in spans]
        lines = [line for line in lines if line] or [""]
        if len(lines) > self.max_lines:
            rest = part(spans[self.max_lines - 1][0])
            lines = lines[:self.max_lines - 1] + [self.fontMetrics().elidedText(rest, Qt.ElideRight, width)]
        return lines or [""]

    def _show(self, width):
        super().setText("\n".join(self._lines(width)))

    def resizeEvent(self, event):
        self._show(event.size().width())
        super().resizeEvent(event)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return len(self._lines(width)) * self.fontMetrics().lineSpacing()

    def sizeHint(self):
        return QSize(320, self.heightForWidth(320))

    def minimumSizeHint(self):
        return QSize(60, self.fontMetrics().lineSpacing())


class EmptyState(QWidget):
    """Liste vide : illustration, titre et sous-titre. Laisse passer la souris (glisser-déposer)."""
    MIN_ART_HEIGHT = 220            # en dessous, seule la phrase reste
    WIDTHS = {"vide": 220}          # largeur de l'illustration ; 160 pour les autres

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.current = None
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        self.art = QLabel()
        self.art.setAlignment(Qt.AlignCenter)
        self.title = QLabel()
        self.subtitle = QLabel()
        for label in (self.title, self.subtitle):
            label.setTextFormat(Qt.PlainText)       # texte de la recherche affiché tel quel
            label.setAlignment(Qt.AlignCenter)
            label.setWordWrap(True)
        for w in (self.art, self.title, self.subtitle):
            lay.addWidget(w)
        lay.addStretch(1)
        self.refresh()

    def show_state(self, illustration, title, subtitle):
        self.title.setText(breakable(title))
        self.subtitle.setText(subtitle)
        if illustration != self.current:
            self.current = illustration
            self.refresh()

    def refresh(self):
        """Couleurs et illustration du thème courant."""
        self.title.setStyleSheet(f"font-weight: 600; font-size: 15px; color: {theme.colors()['text']};")
        self.subtitle.setStyleSheet(f"color: {theme.colors()['muted']};")
        if self.current:
            self.art.setPixmap(theme.illustration(self.current, self.WIDTHS.get(self.current, 160),
                                                  self.devicePixelRatioF()))

    def resizeEvent(self, event):
        self.art.setHidden(event.size().height() < self.MIN_ART_HEIGHT)
        super().resizeEvent(event)


class DetailPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._task = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        self.label = QLabel()
        self.label.setTextFormat(Qt.RichText)
        # liens cliquables, texte non sélectionnable : il contient des coupures invisibles (« Copier le lien »)
        self.label.setTextInteractionFlags(Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard)
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
        folder = html.escape(breakable(task.folder))
        rows = [
            ("Lien", html.escape(breakable(task.url))),
            ("Dossier", f'<a href="{html.escape(QUrl.fromLocalFile(task.folder).toString(), quote=True)}">'
                        f"{folder}</a>"),
            ("Taille", human(task.size)),
            ("Reçu", human(task.done)),
            ("Connexions", f"{task.active_connections} actives / {task.parts} prévues"),
            ("Reprise possible", "—" if task.error else ("oui" if task.resumable else "non")),
        ]
        if task.error:
            rows.append(("Erreur", f"<span style='color:{theme.STATE_COLORS['error']}'>"
                                   f"{html.escape(breakable(task.error))}</span>"))
        name = html.escape(breakable(task.name or task.url))
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
