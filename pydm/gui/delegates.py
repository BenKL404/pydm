# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Rendu de la colonne Progression : barre arrondie colorée selon l'état, puis pourcentage."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate

from . import theme
from .model import PROGRESS_ROLE

BAR_HEIGHT = 6
TEXT_WIDTH = 56
PAD = 8


class ProgressDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawPrimitive(QStyle.PE_PanelItemViewItem, option, painter, option.widget)
        ratio, state = index.data(PROGRESS_ROLE) or (None, "active")
        r = option.rect
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        if ratio is not None:
            track = QRectF(r.left() + PAD, r.center().y() - BAR_HEIGHT / 2 + 1,
                           max(r.width() - TEXT_WIDTH - 2 * PAD, 10), BAR_HEIGHT)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.colors()["border"]))
            painter.drawRoundedRect(track, 3, 3)
            fill = QRectF(track)
            fill.setWidth(track.width() * min(max(ratio, 0.0), 1.0))
            if fill.width() > 0:
                color = theme.accent() if state == "active" else QColor(theme.STATE_COLORS[state])
                painter.setBrush(color)
                painter.drawRoundedRect(fill, 3, 3)
            text_rect = r.adjusted(r.width() - TEXT_WIDTH, 0, -PAD, 0)
            align = Qt.AlignRight | Qt.AlignVCenter
        else:
            text_rect = r.adjusted(PAD, 0, -PAD, 0)
            align = Qt.AlignLeft | Qt.AlignVCenter
        selected = option.state & QStyle.State_Selected
        painter.setPen(option.palette.highlightedText().color() if selected
                       else option.palette.text().color())
        painter.drawText(text_rect, align, index.data(Qt.DisplayRole) or "")
        painter.restore()
