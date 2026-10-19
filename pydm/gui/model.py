# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Modèle Qt du tableau des téléchargements, et filtre de recherche / tri."""
from datetime import datetime

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor

from ..filetypes import category
from ..util import human, human_time
from . import theme

COLUMNS = ("name", "size", "progress", "speed", "eta", "status", "added")
HEADERS = ("Fichier", "Taille", "Progression", "Vitesse", "Restant", "Statut", "Ajouté le")
SORT_ROLE = Qt.UserRole + 1
PROGRESS_ROLE = Qt.UserRole + 2
NUMERIC = (1, 3, 4)


def _ratio(t):
    return t.done / t.size if t.size else None


def _eta(t):
    if t.running and t.size and t.speed > 0:
        return max(t.size - t.done, 0) / t.speed
    return None


def state(t):
    if t.error:
        return "error"
    if t.finished:
        return "done"
    return "active" if t.running else "paused"


class DownloadModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks = []
        self._snaps = []

    @staticmethod
    def _snap(t):
        return (t.name, t.size, t.done, t.speed, t.status, t.running, t.error)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._tasks)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return HEADERS[section]
        return None

    def add(self, task):
        row = len(self._tasks)
        self.beginInsertRows(QModelIndex(), row, row)
        self._tasks.append(task)
        self._snaps.append(self._snap(task))
        self.endInsertRows()

    def remove(self, rows):
        removed = []
        for row in sorted(set(rows), reverse=True):
            self.beginRemoveRows(QModelIndex(), row, row)
            removed.append(self._tasks.pop(row))
            self._snaps.pop(row)
            self.endRemoveRows()
        return removed[::-1]

    def task(self, row):
        return self._tasks[row]

    def tasks(self):
        return list(self._tasks)

    def row_of(self, task):
        return self._tasks.index(task)

    def refresh(self):
        """Signale les lignes dont l'état a changé depuis le dernier appel."""
        for row, t in enumerate(self._tasks):
            snap = self._snap(t)
            if snap != self._snaps[row]:
                self._snaps[row] = snap
                self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMNS) - 1))

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        t, col = self._tasks[index.row()], index.column()
        if role == Qt.DisplayRole:
            return self._text(t, col)
        if role == SORT_ROLE:
            return self._sort_key(t, col)
        if role == PROGRESS_ROLE and col == 2:
            return (_ratio(t), state(t))
        if role == Qt.DecorationRole and col == 0:
            return theme.type_icon(category(t.name))
        if role == Qt.ToolTipRole and col in (0, 5):
            return t.url if col == 0 else t.status
        if role == Qt.ForegroundRole and col == 5 and t.error:
            return QColor(theme.STATE_COLORS["error"])
        if role == Qt.TextAlignmentRole and col in NUMERIC:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    @staticmethod
    def _text(t, col):
        if col == 0:
            return t.name or t.url
        if col == 1:
            return human(t.size)
        if col == 2:
            r = _ratio(t)
            return f"{100 * r:.0f} %" if r is not None else human(t.done)
        if col == 3:
            return f"{human(t.speed)}/s" if t.running else ""
        if col == 4:
            return human_time(_eta(t))
        if col == 5:
            return t.status
        return datetime.fromtimestamp(t.added).strftime("%d/%m/%Y %H:%M")

    @staticmethod
    def _sort_key(t, col):
        if col == 0:
            return (t.name or t.url).lower()
        if col == 1:
            return t.size if t.size is not None else -1
        if col == 2:
            r = _ratio(t)
            return r if r is not None else -1.0
        if col == 3:
            return t.speed if t.running else 0.0
        if col == 4:
            e = _eta(t)
            return e if e is not None else float("inf")
        if col == 5:
            return t.status
        return t.added


class DownloadFilter(QSortFilterProxyModel):
    """Tri sur les valeurs brutes et recherche dans le nom et l'URL."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortRole(SORT_ROLE)
        self._search = ""

    def set_search(self, text):
        if hasattr(self, "beginFilterChange"):     # Qt ≥ 6.9
            self.beginFilterChange()
            self._search = (text or "").strip().lower()
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            self._search = (text or "").strip().lower()
            self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        if not self._search:
            return True
        t = self.sourceModel().task(row)
        return self._search in (t.name or "").lower() or self._search in t.url.lower()
