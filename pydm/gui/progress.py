# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Fenêtre de progression d'un téléchargement, comme IDM : informations, carte des connexions."""
from PySide6.QtCore import QRectF, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QFormLayout, QHBoxLayout, QHeaderView,
                               QLabel, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ..util import human, human_time
from . import theme

FIELDS = ("Lien", "Statut", "Taille", "Reçu", "Vitesse", "Temps restant", "Reprise")


class SegmentMap(QWidget):
    """Le fichier à l'échelle : chaque segment à sa position, sa partie reçue colorée."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.segments, self.size = [], 0
        self.setMinimumHeight(16)

    def sizeHint(self):
        return QSize(400, 16)

    def set_segments(self, segments, size):
        self.segments, self.size = [list(s) for s in segments or []], size or 0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.colors()["border"]))
        p.drawRoundedRect(QRectF(0, 0, w, h), 3, 3)
        if self.size > 0:
            for start, end, got in self.segments:
                if end < start:
                    continue
                x0 = w * start / self.size
                filled = w * min(got, end - start + 1) / self.size
                done = got >= end - start + 1
                p.setBrush(QColor(theme.STATE_COLORS["done"]) if done else theme.accent())
                if filled > 0:
                    p.drawRect(QRectF(x0, 0, filled, h))
                p.setPen(QColor(theme.colors()["window"]))      # séparation entre segments
                p.drawLine(int(x0), 0, int(x0), h)
                p.setPen(Qt.NoPen)
        p.end()


class ProgressDialog(QDialog):
    def __init__(self, task, window, parent=None):
        super().__init__(parent)
        self.task, self.window = task, window
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowIcon(theme.logo())
        self.resize(560, 0)
        self._finished_shown = False
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.values = {}
        for name in FIELDS:
            label = QLabel()
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.values[name] = label
            form.addRow(name, label)
        self.values["Lien"].setText(task.url)
        self.values["Lien"].setWordWrap(True)
        lay.addLayout(form)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        lay.addWidget(self.bar)

        self.details = QWidget()
        d = QVBoxLayout(self.details)
        d.setContentsMargins(0, 0, 0, 0)
        self.map = SegmentMap()
        d.addWidget(self.map)
        self.fragments = QLabel()
        self.fragments.setStyleSheet(f"color: {theme.colors()['muted']};")
        d.addWidget(self.fragments)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["N°", "Reçu", "Reste", "État"])
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setMinimumHeight(140)
        self.table.setMaximumHeight(200)
        d.addWidget(self.table)
        lay.addWidget(self.details)

        foot = QHBoxLayout()
        self.close_box = QCheckBox("Fermer à la fin")
        foot.addWidget(self.close_box)
        foot.addStretch(1)
        self.open_btn = QPushButton("Ouvrir le fichier")
        self.open_btn.clicked.connect(lambda: self.window.open_file(self.task))
        self.folder_btn = QPushButton("Ouvrir le dossier")
        self.folder_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.task.folder)))
        self.details_btn = QPushButton("Masquer les détails")
        self.details_btn.clicked.connect(self._toggle_details)
        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.clicked.connect(self._cancel)
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setObjectName("primary")
        self.pause_btn.clicked.connect(self._pause_resume)
        for b in (self.open_btn, self.folder_btn, self.details_btn, self.cancel_btn, self.pause_btn):
            foot.addWidget(b)
        self.open_btn.hide()
        self.folder_btn.hide()
        lay.addLayout(foot)

    # --- actions -----------------------------------------------------------------
    def _toggle_details(self):
        self.details.setVisible(self.details.isHidden())
        self.details_btn.setText("Masquer les détails" if not self.details.isHidden() else "Afficher les détails")
        self.adjustSize()

    def _pause_resume(self):
        if self.task.running or self.task.want in ("now", "later", "force"):
            self.window.pause_task(self.task)
        else:
            self.window.resume_task(self.task)
        self.refresh()

    def _cancel(self):
        """Annuler = arrêter ce téléchargement (rien n'est supprimé) et fermer la fenêtre."""
        if not self.task.finished:
            self.window.pause_task(self.task)
        self.close()

    # --- affichage ----------------------------------------------------------------
    def refresh(self):
        t = self.task
        ratio = t.done / t.size if t.size else None
        pct = f"{100 * ratio:.0f} %" if ratio is not None else ""
        name = t.name or t.url
        self.values["Statut"].setText(t.status)
        self.values["Taille"].setText(human(t.size))
        self.values["Reçu"].setText(f"{human(t.done)}" + (f" ({pct})" if pct else ""))
        self.values["Vitesse"].setText(f"{human(t.speed)}/s" if t.running else "")
        eta = (t.size - t.done) / t.speed if t.running and t.size and t.speed > 0 else None
        self.values["Temps restant"].setText(human_time(eta))
        self.values["Reprise"].setText("—" if t.error else ("possible" if t.resumable else "impossible"))
        self.bar.setValue(int(1000 * ratio) if ratio is not None else 0)
        segments = getattr(t, "segments", None)
        has_map = bool(segments) and t.size
        self.map.setVisible(bool(has_map))
        self.table.setVisible(bool(has_map))
        self.fragments.setVisible(not has_map)
        if has_map:
            self.map.set_segments(segments, t.size)
            self._fill_table(segments)
        else:
            self.fragments.setText(t.status)
        running = t.running or t.want in ("now", "later", "force")
        self.pause_btn.setText("Pause" if running else "Reprendre")
        if t.finished:
            self._show_finished(name)
        else:
            self.setWindowTitle(f"{pct + ' · ' if pct else ''}{name}")

    def _fill_table(self, segments):
        self.table.setRowCount(len(segments))
        for row, (start, end, got) in enumerate(segments):
            left = max(end - start + 1 - got, 0) if end >= start else 0
            state = "terminée" if end >= start and left == 0 else ("réception" if self.task.running else "en attente")
            for col, text in enumerate((str(row + 1), human(got), human(left), state)):
                item = self.table.item(row, col)
                if item is None:
                    item = QTableWidgetItem()
                    self.table.setItem(row, col, item)
                item.setText(text)
                if col == 3:
                    item.setForeground(QColor(theme.STATE_COLORS["done"]) if state == "terminée"
                                       else QColor(theme.colors()["text"]))

    def _show_finished(self, name):
        if self._finished_shown:
            return
        self._finished_shown = True
        if self.close_box.isChecked():
            self.close()
            return
        self.setWindowTitle(f"Terminé · {name}")
        self.values["Statut"].setText("Terminé")
        self.pause_btn.hide()
        self.details_btn.hide()
        self.open_btn.show()
        self.folder_btn.show()
        self.cancel_btn.setText("Fermer")
