# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Modèle Qt du tableau des téléchargements, et filtre de recherche / tri."""
from datetime import datetime

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor

from ..engine import VideoDownload
from ..filetypes import CATEGORIES, category
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


STATES = ("all", "active", "queued", "paused", "done", "error")


def task_state(t):
    """État affiché dans la barre latérale."""
    if t.error:
        return "error"
    if t.finished:
        return "done"
    if t.running:
        return "active"
    return "queued" if t.want in ("now", "later", "force") else "paused"


def task_category(t):
    """Catégorie de rangement : une vidéo de streaming est « video » (« music » en Audio MP3)."""
    if isinstance(t, VideoDownload):
        return "music" if t.quality == "Audio MP3" else "video"
    return category(t.name)


def counts(tasks):
    """Compteurs (par état, par catégorie) pour la barre latérale."""
    states = dict.fromkeys(STATES, 0)
    types = dict.fromkeys(("all",) + CATEGORIES, 0)
    for t in tasks:
        states["all"] += 1
        states[task_state(t)] += 1
        types["all"] += 1
        types[task_category(t)] += 1
    return states, types


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

    def replace(self, old, new):
        row = self._tasks.index(old)
        self._tasks[row] = new
        self._snaps[row] = self._snap(new)
        self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMNS) - 1))

    def move(self, rows, delta):
        """Décale les lignes d'un cran (delta ±1) ; renvoie leurs nouvelles positions."""
        self.layoutAboutToBeChanged.emit()
        taken, new = set(), []
        for r in sorted(set(rows), reverse=delta > 0):
            t = r + delta
            if 0 <= t < len(self._tasks) and t not in taken:
                for lst in (self._tasks, self._snaps):
                    lst[r], lst[t] = lst[t], lst[r]
                r = t
            taken.add(r)
            new.append(r)
        self.layoutChanged.emit()
        return sorted(new)

    def move_to_top(self, rows):
        rows = sorted(set(rows))
        self.layoutAboutToBeChanged.emit()
        for lst in (self._tasks, self._snaps):
            lst[:] = [lst[r] for r in rows] + [x for i, x in enumerate(lst) if i not in rows]
        self.layoutChanged.emit()
        return list(range(len(rows)))

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
            return theme.type_icon(task_category(t))
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
        self._search, self._state, self._type = "", "all", "all"

    def _change(self, attr, value):
        if hasattr(self, "beginFilterChange"):     # Qt ≥ 6.9
            self.beginFilterChange()
            setattr(self, attr, value)
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            setattr(self, attr, value)
            self.invalidateFilter()

    def set_search(self, text):
        self._change("_search", (text or "").strip().lower())

    def set_state(self, key):
        self._change("_state", key)

    def set_type(self, key):
        self._change("_type", key)

    def refilter(self):
        """Les états changent en continu : réévaluer le filtre (appelé à chaque rafraîchissement)."""
        if self._state != "all":
            self._change("_state", self._state)

    def filterAcceptsRow(self, row, parent):
        t = self.sourceModel().task(row)
        if self._state != "all" and task_state(t) != self._state:
            return False
        if self._type != "all" and task_category(t) != self._type:
            return False
        if not self._search:
            return True
        return self._search in (t.name or "").lower() or self._search in t.url.lower()
