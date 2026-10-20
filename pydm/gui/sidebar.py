# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Barre latérale : filtres par état et par type de fichier, avec compteurs."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QLabel, QMenu, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from . import theme

STATE_ENTRIES = (("all", "Tous"), ("active", "En cours"), ("queued", "En file"), ("paused", "En pause"),
                 ("done", "Terminés"), ("error", "En erreur"))
TYPE_ENTRIES = (("all", "Tous"), ("video", "Vidéos"), ("music", "Musique"), ("document", "Documents"),
                ("image", "Images"), ("archive", "Archives"), ("program", "Programmes"), ("other", "Autres"))


def _dot(color):
    pix = QPixmap(16, 16)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(4, 4, 8, 8)
    p.end()
    return QIcon(pix)


class Sidebar(QWidget):
    filter_changed = Signal(str, str)       # (état, type)
    folder_requested = Signal(str)          # catégorie dont il faut ouvrir le dossier

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(150)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 0, 8)
        lay.setSpacing(4)
        self.state_tree = self._tree(STATE_ENTRIES, self._state_icon)
        self.type_tree = self._tree(TYPE_ENTRIES, self._type_icon)
        self.type_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.type_tree.customContextMenuRequested.connect(self._type_menu)
        for title, tree in (("ÉTAT", self.state_tree), ("TYPE", self.type_tree)):
            label = QLabel(title)
            label.setStyleSheet(f"color: {theme.colors()['muted']}; font-size: 10px; font-weight: 600;"
                                " letter-spacing: 1px; padding-left: 6px;")
            lay.addWidget(label)
            lay.addWidget(tree)
        lay.addStretch(1)

    @staticmethod
    def _state_icon(key):
        colors = {"active": theme.colors()["accent"], "queued": "#60a5fa", "paused": theme.STATE_COLORS["paused"],
                  "done": theme.STATE_COLORS["done"], "error": theme.STATE_COLORS["error"]}
        return _dot(colors[key]) if key in colors else theme.icon("menu")

    @staticmethod
    def _type_icon(key):
        return theme.type_icon(key) if key != "all" else theme.icon("folder")

    def _tree(self, entries, icon):
        tree = QTreeWidget()
        tree.setColumnCount(2)
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(False)
        tree.setIndentation(0)
        tree.setFrameShape(QTreeWidget.NoFrame)
        tree.setStyleSheet("QTreeWidget { background: transparent; }")
        tree.setSelectionMode(QAbstractItemView.SingleSelection)
        tree.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tree.setFocusPolicy(Qt.NoFocus)
        for key, label in entries:
            item = QTreeWidgetItem([label, ""])
            item.setIcon(0, icon(key))
            item.setData(0, Qt.UserRole, key)
            item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            tree.addTopLevelItem(item)
        tree.setCurrentItem(tree.topLevelItem(0))
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        head = tree.header()
        head.setStretchLastSection(False)
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        head.setSectionResizeMode(1, QHeaderView.Fixed)
        head.resizeSection(1, 40)
        rows = tree.topLevelItemCount()
        tree.setFixedHeight(rows * (tree.sizeHintForRow(0) + 2) + 4)
        tree.currentItemChanged.connect(lambda *_: self.filter_changed.emit(self.state_key(), self.type_key()))
        return tree

    def state_key(self):
        item = self.state_tree.currentItem()
        return item.data(0, Qt.UserRole) if item else "all"

    def type_key(self):
        item = self.type_tree.currentItem()
        return item.data(0, Qt.UserRole) if item else "all"

    def update_counts(self, states, types):
        muted = QColor(theme.colors()["muted"])
        for tree, values in ((self.state_tree, states), (self.type_tree, types)):
            for i in range(tree.topLevelItemCount()):
                item = tree.topLevelItem(i)
                n = values.get(item.data(0, Qt.UserRole), 0)
                item.setText(1, str(n))
                item.setForeground(1, muted)
                item.setForeground(0, muted if n == 0 else QColor(theme.colors()["text"]))

    def _type_menu(self, pos):
        item = self.type_tree.itemAt(pos)
        if not item:
            return
        key = item.data(0, Qt.UserRole)
        menu = QMenu(self)
        menu.addAction(theme.icon("folder"), "Ouvrir le dossier",
                       lambda: self.folder_requested.emit("other" if key == "all" else key))
        menu.exec(self.type_tree.viewport().mapToGlobal(pos))
