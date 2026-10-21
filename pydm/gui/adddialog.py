# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Fenêtre d'ajout : ce qui va être téléchargé, choix de la qualité, du nom et du dossier."""
import os
import queue
import threading
import time
import urllib.request

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QTableWidget,
                               QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from .. import store
from ..analyze import THUMB_MAX, analyze
from ..cache import video_key
from ..engine import UA
from ..engine import QUALITIES
from ..filetypes import category
from ..util import human, human_time, safe_filename
from . import theme

TIMEOUT = 30
TYPE_NAMES = {"video": "Vidéo", "music": "Musique", "document": "Document", "image": "Image", "archive": "Archive",
              "program": "Programme", "other": "Fichier"}


def fetch_youtube_thumbnail(video_id):
    """Miniature YouTube (adresse déduite de l'identifiant) : 64 Ko et 5 s au plus."""
    url = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=5) as r:
            data = r.read(THUMB_MAX + 1)
    except Exception:  # noqa: BLE001
        return None
    return data if len(data) <= THUMB_MAX else None


class AddDialog(QDialog):
    accepted_tasks = Signal(list, bool)     # entrées à créer, démarrer (Télécharger) ou non (Plus tard)

    def __init__(self, settings, urls, headers=None, filename=None, kind="auto", parent=None,
                 analyzer=analyze, title=None, thumb_fetcher=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowIcon(theme.logo())
        self.settings, self.urls, self.headers = settings, list(urls), headers
        self.filename, self.kind, self.analyzer = filename, kind, analyzer
        self.results = [None] * len(self.urls)
        self.results_q = queue.Queue()      # (index, résultat) issus des threads d'analyse
        self.thumb_q = queue.Queue()        # miniature YouTube chargée sans attendre l'analyse
        self.has_thumb = False
        self.page_title = title
        self.closed = False
        self.started_at = time.monotonic()
        self.batch = len(self.urls) > 1
        if self.batch:
            self._build_batch()
        else:
            self._build_single()
        for i, url in enumerate(self.urls):
            threading.Thread(target=self._analyze, args=(i, url), daemon=True).start()
        key = video_key(self.urls[0])
        if not self.batch and key.startswith("youtube:"):
            vid = key.split(":", 1)[1]
            thumb_fetcher = thumb_fetcher or fetch_youtube_thumbnail
            threading.Thread(target=lambda: self.thumb_q.put(thumb_fetcher(vid)), daemon=True).start()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(200)

    # --- construction -----------------------------------------------------------
    def _footer(self):
        foot = QHBoxLayout()
        self.never_box = QCheckBox("Ne plus demander")
        foot.addWidget(self.never_box)
        foot.addStretch(1)
        cancel = QPushButton("Annuler")
        cancel.clicked.connect(self.reject)
        self.later_btn = QPushButton("Plus tard")
        self.later_btn.clicked.connect(lambda: self._finish(False))
        self.download_btn = QPushButton("Télécharger")
        self.download_btn.setObjectName("primary")
        self.download_btn.setDefault(True)
        self.download_btn.clicked.connect(lambda: self._finish(True))
        for b in (cancel, self.later_btn, self.download_btn):
            foot.addWidget(b)
        return foot

    def _folder_row(self):
        self.folder_edit = QLineEdit(self.settings["folder"])
        browse = QToolButton()
        browse.setIcon(theme.icon("folder"))
        browse.setToolTip("Choisir le dossier")
        browse.clicked.connect(self._browse)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.folder_edit, 1)
        h.addWidget(browse)
        return row

    def _build_single(self):
        self.setWindowTitle("Ajouter un téléchargement")
        self.resize(560, 0)
        lay = QVBoxLayout(self)
        head = QHBoxLayout()
        self.thumb = QLabel()
        self.thumb.setFixedSize(QSize(128, 72))
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setPixmap(theme.type_icon("other").pixmap(32, 32))
        head.addWidget(self.thumb)
        text = QVBoxLayout()
        self.title_label = QLabel(self.page_title or self.urls[0])
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        self.info_label = QLabel("Analyse…")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet(f"color: {theme.colors()['muted']};")
        text.addWidget(self.title_label)
        text.addWidget(self.info_label)
        text.addStretch(1)
        head.addLayout(text, 1)
        lay.addLayout(head)
        form = QFormLayout()
        self.quality_box = QComboBox()
        self.quality_box.setEnabled(False)
        self.quality_box.currentIndexChanged.connect(self._quality_changed)
        self.quality_label = QLabel("Qualité")
        form.addRow(self.quality_label, self.quality_box)
        self.name_edit = QLineEdit(self.filename or "")
        form.addRow("Nom", self.name_edit)
        self.folder_label = QLabel("Dossier")
        form.addRow(self.folder_label, self._folder_row())
        lay.addLayout(form)
        self.ffmpeg_label = QLabel("Installez ffmpeg pour les meilleures qualités")
        self.ffmpeg_label.setStyleSheet(f"color: {theme.colors()['muted']}; font-size: 11px;")
        self.ffmpeg_label.hide()
        lay.addWidget(self.ffmpeg_label)
        lay.addLayout(self._footer())

    def _build_batch(self):
        self.setWindowTitle(f"Ajouter {len(self.urls)} téléchargements")
        self.resize(620, 420)
        lay = QVBoxLayout(self)
        t = QTableWidget(len(self.urls), 3)
        t.setHorizontalHeaderLabels(["", "Fichier", "Taille"])
        t.verticalHeader().hide()
        t.setShowGrid(False)
        t.setSelectionMode(QAbstractItemView.NoSelection)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        t.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        t.setColumnWidth(0, 28)
        t.setColumnWidth(2, 110)
        for row, url in enumerate(self.urls):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(Qt.Checked)
            t.setItem(row, 0, check)
            name = QTableWidgetItem(theme.type_icon("other"), url.rstrip("/").rsplit("/", 1)[-1] or url)
            name.setToolTip(url)
            t.setItem(row, 1, name)
            size = QTableWidgetItem("Analyse…")
            size.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            t.setItem(row, 2, size)
        t.itemChanged.connect(lambda *_: self._update_count())
        self.table = t
        lay.addWidget(t, 1)
        form = QFormLayout()
        self.videos_box = QComboBox()
        self.videos_box.addItems(list(QUALITIES))
        self.videos_box.setCurrentText(self.settings["quality"])
        form.addRow("Vidéos", self.videos_box)
        self.folder_label = QLabel("Dossier principal" if self.settings.get("sort_by_type", True) else "Dossier")
        form.addRow(self.folder_label, self._folder_row())
        lay.addLayout(form)
        lay.addLayout(self._footer())
        self._update_count()

    def _checked_rows(self):
        return [row for row in range(self.table.rowCount())
                if self.table.item(row, 0).checkState() == Qt.Checked]

    def _update_count(self):
        n = len(self._checked_rows())
        self.download_btn.setText(f"Télécharger {n}")
        self.download_btn.setEnabled(n > 0)
        self.later_btn.setEnabled(n > 0)

    def _show_row(self, row, r):
        name, size = self.table.item(row, 1), self.table.item(row, 2)
        if r["kind"] == "error":
            self.table.item(row, 0).setCheckState(Qt.Unchecked)
            name.setToolTip(f"{self.urls[row]}\n{r['error']}")
            size.setText("Erreur")
            size.setForeground(QColor(theme.STATE_COLORS["error"]))
            return
        name.setText(r["name"] or self.urls[row])
        name.setIcon(theme.type_icon("video" if r["kind"] == "video" else category(r["name"])))
        size.setText(human(r["size"]) if r.get("size") else ("" if r["kind"] == "video" else "?"))

    # --- analyse ----------------------------------------------------------------
    def _analyze(self, i, url):
        r = self.analyzer(url, self.headers, self.settings["browser"], self.kind, self.settings["quality"])
        self.results_q.put((i, r))

    def done_count(self):
        return sum(r is not None for r in self.results)

    def poll(self):
        """Intègre les résultats arrivés (appelé par le minuteur) ; rien après la fermeture."""
        while not self.thumb_q.empty():
            data = self.thumb_q.get()
            if data and not self.closed and not self.has_thumb:
                self._show_thumbnail(data)
        while not self.results_q.empty():
            i, r = self.results_q.get()
            if not self.closed and self.results[i] is None:
                self._set_result(i, r)
        if not self.closed and time.monotonic() - self.started_at > TIMEOUT:
            for i, r in enumerate(self.results):
                if r is None:
                    self._set_result(i, {"kind": "error", "error": "Analyse trop longue", "drm": False,
                                         "choices": [], "name": None})

    def _set_result(self, i, r):
        self.results[i] = r
        if self.batch:
            self._show_row(i, r)
        else:
            self._show_single(r)

    def _show_single(self, r):
        muted = theme.colors()["muted"]
        if r["kind"] == "error":
            self.info_label.setText(r["error"])
            self.info_label.setStyleSheet(f"color: {theme.STATE_COLORS['error']};")
            if r.get("drm"):
                self.download_btn.setEnabled(False)
                self.later_btn.setEnabled(False)
            else:
                self.download_btn.setText("Télécharger quand même")
            self._hide_quality()
            return
        self.info_label.setStyleSheet(f"color: {muted};")
        if not self.name_edit.isModified():
            self.name_edit.setText(r["name"] or "")
        if r["kind"] == "video":
            self.setWindowTitle("Ajouter une vidéo")
            self.title_label.setText(r.get("title") or self.page_title or self.urls[0])
            parts = [r.get("site")] + ([human_time(r["duration"])] if r.get("duration") else [])
            self.info_label.setText(" · ".join(p for p in parts if p))
            self.quality_box.blockSignals(True)
            self.quality_box.clear()
            self.quality_box.addItems([c["label"] for c in r["choices"]])
            self.quality_box.setCurrentIndex(r["selected"])
            self.quality_box.blockSignals(False)
            self.quality_box.setEnabled(True)
            self.ffmpeg_label.setVisible(bool(r.get("ffmpeg_missing")))
            if r.get("thumbnail") or not self.has_thumb:
                self._show_thumbnail(r.get("thumbnail"))
            self._update_folder()
        else:
            self.title_label.setText(r["name"] or self.urls[0])
            cat = category(r["name"])
            self.thumb.setPixmap(theme.type_icon(cat).pixmap(40, 40))
            info = [r.get("site"), human(r.get("size")), TYPE_NAMES[cat],
                    "reprise possible" if r.get("resumable") else "sans reprise",
                    f"{self.settings['parts']} connexions" if r.get("resumable") else "1 connexion"]
            self.info_label.setText(" · ".join(p for p in info if p))
            self._hide_quality()
            self._update_folder()

    def _hide_quality(self):
        self.quality_label.hide()
        self.quality_box.hide()

    def _show_thumbnail(self, data):
        pix = QPixmap()
        if data and pix.loadFromData(data):
            self.thumb.setPixmap(pix.scaled(128, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.has_thumb = True
        elif self.has_thumb:
            return                  # image illisible : on garde la bonne miniature déjà affichée
        else:
            self.thumb.setPixmap(theme.type_icon("video").pixmap(40, 40))

    def _category(self, r, choice=None):
        """Catégorie de rangement d'un résultat d'analyse (None si inconnue)."""
        if not r or r["kind"] == "error":
            return None
        if r["kind"] == "video":
            return "music" if choice and choice["audio_only"] else "video"
        return category(r["name"])

    def _current_choice(self):
        r = self.results[0]
        i = self.quality_box.currentIndex()
        return r["choices"][i] if r and r["kind"] == "video" and 0 <= i < len(r["choices"]) else None

    def _update_folder(self):
        """Dossier de la catégorie, tant que l'utilisateur n'a pas choisi le sien."""
        cat = self._category(self.results[0], self._current_choice())
        if cat and not self.folder_edit.isModified():
            self.folder_edit.setText(store.folder_for(cat, self.settings))

    def _quality_changed(self, index):
        self._update_folder()
        r = self.results[0]
        if not r or r["kind"] != "video" or self.name_edit.isModified() or index < 0:
            return
        stem = os.path.splitext(self.name_edit.text())[0] or os.path.splitext(r["name"] or "video")[0]
        self.name_edit.setText(f"{stem}.{r['choices'][index]['ext']}")

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Dossier de téléchargement", self.folder_edit.text())
        if path:
            self.folder_edit.setText(path)

    # --- résultat ----------------------------------------------------------------
    def collect(self):
        """Entrées à créer selon l'état de la fenêtre."""
        if self.batch:
            return self._collect_batch()
        r = self.results[0]
        kind = r["kind"] if r and r["kind"] in ("video", "file") else self.kind
        choice = None
        if r and r["kind"] == "video" and self.quality_box.currentIndex() >= 0:
            choice = r["choices"][self.quality_box.currentIndex()]
        name = safe_filename(self.name_edit.text().strip() or (r and r.get("name")) or self.filename or "", fallback="")
        audio_mp3 = bool(choice and choice["audio_only"] and choice["ext"] == "mp3")
        auto = self._category(r, choice) is None and not self.folder_edit.isModified()
        return [{"url": self.urls[0], "kind": kind, "folder": self.folder_edit.text().strip() or self.settings["folder"],
                 "auto_folder": auto,
                 "name": name, "fmt": choice["format"] if choice else None,
                 "quality": "Audio MP3" if audio_mp3 else ("Meilleure" if choice else self.settings["quality"]),
                 "headers": self.headers, "filename": self.filename, "ext": choice["ext"] if choice else None}]

    def _collect_batch(self):
        main = self.folder_edit.text().strip() or self.settings["folder"]
        mp3 = self.videos_box.currentText() == "Audio MP3"
        tasks = []
        for row in self._checked_rows():
            r = self.results[row]
            kind = r["kind"] if r and r["kind"] in ("video", "file") else self.kind
            cat = self._category(r, {"audio_only": True} if mp3 else None)
            folder = store.folder_for(cat, {**self.settings, "folder": main}) if cat else main
            tasks.append({"url": self.urls[row], "kind": kind, "folder": folder, "auto_folder": cat is None,
                          "name": (r and r.get("name")) or None, "fmt": None,
                          "quality": self.videos_box.currentText(), "headers": self.headers, "filename": None})
        return tasks

    def _finish(self, start):
        tasks = self.collect()
        for folder in dict.fromkeys(os.path.expanduser(t["folder"]) for t in tasks):
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError as e:
                QMessageBox.warning(self, "PyDM", f"Dossier inutilisable : {folder}\n{e.strerror or e}")
                return      # la fenêtre reste ouverte avec les choix de l'utilisateur
        if self.never_box.isChecked():
            self.settings["confirm_add"] = False
            store.save_settings(self.settings)
        self.closed = True
        self.accepted_tasks.emit(tasks, start)
        self.accept()

    def done(self, result):
        self.closed = True
        self.timer.stop()
        super().done(result)
