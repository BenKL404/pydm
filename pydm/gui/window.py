# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Fenêtre principale : barre d'en-tête, tableau des téléchargements, barre d'état."""
import os
import queue
import threading
import time

from PySide6.QtCore import QByteArray, QEvent, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMenu, QMessageBox, QPushButton, QSplitter, QTableView,
                               QToolButton, QVBoxLayout, QWidget)

from .. import __version__, ipc, store
from ..util import human
from ..engine import BROWSERS, QUALITIES, Download, entry_from_task, make_download, task_from_entry
from . import theme
from .delegates import ProgressDelegate
from .links import extract_urls
from .model import DownloadFilter, DownloadModel
from .widgets import DetailPanel, SpeedSparkline

WIDTHS = (300, 80, 190, 90, 80, 170, 120)


class MainWindow(QMainWindow):
    def __init__(self, settings, factory=make_download):
        super().__init__()
        self.settings = settings
        self.factory = factory
        self.inbox = queue.Queue()      # messages de l'extension (thread IPC)
        self.detected = queue.Queue()   # (ligne provisoire, tâche) issus des threads de détection
        self.dirty = False
        self.setWindowTitle("PyDM")
        self.setWindowIcon(theme.logo())
        self.resize(1100, 600)

        self.model = DownloadModel(self)
        self.proxy = DownloadFilter(self)
        self.proxy.setSourceModel(self.model)
        self._build_header()
        self._build_table()
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.header)
        lay.addWidget(self.search)
        self.detail = DetailPanel()
        self.vsplit = QSplitter(Qt.Vertical)
        self.vsplit.addWidget(self.table)
        self.vsplit.addWidget(self.detail)
        self.vsplit.setStretchFactor(0, 1)
        self.vsplit.setCollapsible(0, False)
        self.vsplit.setSizes([440, 130])
        self.hsplit = QSplitter(Qt.Horizontal)     # la barre latérale s'y ajoutera (étape 3)
        self.hsplit.addWidget(self.vsplit)
        lay.addWidget(self.hsplit, 1)
        self.setCentralWidget(central)
        self.status_left = QLabel()
        self.status_left.setContentsMargins(8, 0, 0, 0)
        self.statusBar().addWidget(self.status_left, 1)
        self.sparkline = SpeedSparkline()
        self.status_speed = QLabel()
        self.status_speed.setContentsMargins(0, 0, 8, 0)
        self.statusBar().addPermanentWidget(self.sparkline)
        self.statusBar().addPermanentWidget(self.status_speed)
        self._last_sample = 0.0
        self.setAcceptDrops(True)
        self._shortcuts()

        self._restore_state()
        self._load_session()
        QGuiApplication.clipboard().dataChanged.connect(self._clipboard_changed)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(500)
        self._update_actions()

    # --- construction ------------------------------------------------------
    def _tool(self, icon, tip, slot, shortcut=None):
        b = QToolButton()
        b.setIcon(theme.icon(icon))
        b.setIconSize(QSize(20, 20))
        b.setToolTip(tip + (f"  ({shortcut})" if shortcut else ""))
        b.clicked.connect(slot)
        b.setAutoRaise(True)
        b.setProperty("icon_name", icon)
        return b

    def _build_header(self):
        self.header = QFrame()
        self.header.setObjectName("header")
        h = QHBoxLayout(self.header)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(6)
        self.link = QLineEdit()
        self.link.setPlaceholderText("Coller un lien ou glisser-déposer…")
        self.link.setClearButtonEnabled(True)
        self.link.returnPressed.connect(self.download_link)
        h.addWidget(self.link, 1)
        self.quality = QComboBox()
        self.quality.addItems(list(QUALITIES))
        self.quality.setCurrentText(self.settings["quality"])
        self.quality.setToolTip("Qualité des vidéos de streaming")
        self.quality.currentTextChanged.connect(lambda v: self._set("quality", v))
        h.addWidget(self.quality)
        self.cookies = QComboBox()
        self.cookies.addItems(list(BROWSERS))
        self.cookies.setCurrentText(self.settings["browser"])
        self.cookies.setToolTip("Utiliser les cookies de ce navigateur")
        self.cookies.currentTextChanged.connect(lambda v: self._set("browser", v))
        h.addWidget(self.cookies)
        go = QPushButton("Télécharger")
        go.setObjectName("primary")
        go.clicked.connect(self.download_link)
        h.addWidget(go)
        h.addSpacing(8)
        self.btn_resume = self._tool("resume", "Reprendre", self.resume_selected)
        self.btn_pause = self._tool("pause", "Pause", self.pause_selected)
        self.btn_remove = self._tool("remove", "Retirer de la liste", self.remove_selected, "Suppr")
        self.btn_folder = self._tool("folder", "Ouvrir le dossier", self.open_folder, "Ctrl+O")
        for b in (self.btn_resume, self.btn_pause, self.btn_remove, self.btn_folder):
            h.addWidget(b)
        h.addSpacing(8)
        self.btn_search = self._tool("search", "Rechercher", self.toggle_search, "Ctrl+F")
        h.addWidget(self.btn_search)
        self.btn_menu = self._tool("menu", "Menu", lambda: None)
        self.menu = QMenu(self)
        self.menu.addAction("À propos de PyDM", self.about)
        self.menu.addSeparator()
        self.menu.addAction("Quitter", self.quit_app)
        self.btn_menu.setMenu(self.menu)
        self.btn_menu.setPopupMode(QToolButton.InstantPopup)
        h.addWidget(self.btn_menu)
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Rechercher dans les noms et les liens…  (Échap pour fermer)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.proxy.set_search)
        self.search.installEventFilter(self)
        self.search.hide()

    def _build_table(self):
        t = QTableView()
        t.setModel(self.proxy)
        t.setItemDelegateForColumn(2, ProgressDelegate(t))
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.ExtendedSelection)
        t.setAlternatingRowColors(True)
        t.setShowGrid(False)
        t.setSortingEnabled(True)
        t.setWordWrap(False)
        t.setIconSize(QSize(18, 18))
        t.verticalHeader().hide()
        t.verticalHeader().setDefaultSectionSize(int(t.fontMetrics().height() * 1.8))
        t.horizontalHeader().setHighlightSections(False)
        t.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        t.horizontalHeader().setStretchLastSection(True)
        t.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        for col, width in enumerate(WIDTHS):
            t.setColumnWidth(col, width)
        t.selectionModel().selectionChanged.connect(lambda *_: self._selection_changed())
        t.setContextMenuPolicy(Qt.CustomContextMenu)
        t.customContextMenuRequested.connect(self._context_menu)
        t.doubleClicked.connect(self._double_click)
        t.installEventFilter(self)
        self.empty = QLabel("Collez un lien ou glissez-le ici pour commencer", t.viewport())
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet(f"color: {theme.colors()['muted']}; font-size: 14px;")
        t.viewport().installEventFilter(self)
        self.table = t

    def _shortcuts(self):
        for keys, slot in ((QKeySequence.Find, self.toggle_search), ("Ctrl+O", self.open_folder),
                           (QKeySequence.Quit, self.quit_app), ("Ctrl+Q", self.quit_app)):
            QShortcut(QKeySequence(keys), self, slot)

    def eventFilter(self, obj, event):
        table = getattr(self, "table", None)        # le champ de recherche existe avant le tableau
        if table is not None and obj is table.viewport() and event.type() == QEvent.Resize:
            self.empty.resize(event.size())
        elif obj is table and event.type() == QEvent.KeyPress:
            key, mods = event.key(), event.modifiers()
            if event.matches(QKeySequence.Paste):
                self.paste_links()
                return True
            if key == Qt.Key_Space and not mods:
                self.toggle_selected()
                return True
            if key == Qt.Key_Delete and not mods:
                self.remove_selected()
                return True
        elif obj is self.search and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.toggle_search(False)
            return True
        return super().eventFilter(obj, event)

    # --- glisser-déposer, collage, recherche ---------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasText() or event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.drop_mime(event.mimeData())
        event.acceptProposedAction()

    def drop_mime(self, mime):
        text = mime.text() if mime.hasText() else ""
        if mime.hasUrls():
            text += "\n" + "\n".join(u.toString() for u in mime.urls())
        urls = extract_urls(text)
        if urls:
            self.add_urls(urls)

    def paste_links(self):
        urls = extract_urls(QGuiApplication.clipboard().text())
        if urls:
            self.add_urls(urls)

    def toggle_search(self, show=None):
        show = not self.search.isVisible() if show is None else show
        self.search.setVisible(show)
        if show:
            self.search.setFocus()
            self.search.selectAll()
        else:
            self.search.clear()
            self.table.setFocus()

    # --- réglages et état de la fenêtre -------------------------------------
    def _set(self, key, value):
        self.settings[key] = value
        store.save_settings(self.settings)

    def _restore_state(self):
        w = self.settings.get("window") or {}
        for key, restore in (("geometry", self.restoreGeometry),
                             ("header", self.table.horizontalHeader().restoreState),
                             ("splitter", self.vsplit.restoreState)):
            if w.get(key):
                restore(QByteArray.fromBase64(w[key].encode()))

    def _save_state(self):
        self.settings["window"] = {
            "geometry": bytes(self.saveGeometry().toBase64()).decode(),
            "header": bytes(self.table.horizontalHeader().saveState().toBase64()).decode(),
            "splitter": bytes(self.vsplit.saveState().toBase64()).decode(),
        }
        store.save_settings(self.settings)

    # --- session ---------------------------------------------------------------
    def _load_session(self):
        for e in store.load_session():
            try:
                t = task_from_entry(e)
            except (KeyError, TypeError, ValueError):
                continue
            if t.status == "En attente":
                t.status = "En pause"
            self.model.add(t)

    def save_session(self):
        store.save_session([entry_from_task(t) for t in self.model.tasks() if t.status != "Analyse…"])

    # --- ajout ---------------------------------------------------------------
    def download_link(self):
        urls = extract_urls(self.link.text())
        if not urls:
            if self.link.text().strip():
                QMessageBox.warning(self, "PyDM", "Entrez un lien http(s) ou ftp valide.")
            return
        self.link.clear()
        self.add_urls(urls)

    def add_urls(self, urls, headers=None, filename=None, kind="auto"):
        folder = os.path.expanduser(self.settings["folder"])
        parts, quality, browser = self.settings["parts"], self.settings["quality"], self.settings["browser"]
        for url in urls:
            placeholder = Download(url, folder, parts)
            placeholder.status = "Analyse…"
            self.model.add(placeholder)

            def detect(url=url, placeholder=placeholder):    # réseau : hors du thread de l'interface
                try:
                    task = self.factory(url, folder, parts, quality, browser, headers, filename, kind)
                except Exception as e:  # noqa: BLE001
                    placeholder.error = str(e)
                    placeholder.status = f"Erreur : {e}"
                    return
                self.detected.put((placeholder, task))
            threading.Thread(target=detect, daemon=True).start()
        self._update_actions()

    def handle_message(self, msg):
        """Appelé par le thread IPC : on se contente de transmettre au thread de l'interface."""
        self.inbox.put(msg)
        return {"ok": True}

    def _clipboard_changed(self):
        if not self.settings["clipboard"] or self.link.text():
            return
        urls = extract_urls(QGuiApplication.clipboard().text())
        if len(urls) == 1:
            self.link.setText(urls[0])

    # --- boucle périodique ----------------------------------------------------
    def tick(self):
        while not self.inbox.empty():
            msg = self.inbox.get()
            if msg.get("action") == "add" and msg.get("url"):
                self.add_urls([msg["url"]], msg.get("headers"), msg.get("filename"), msg.get("kind", "auto"))
            self.show_window()
        while not self.detected.empty():
            placeholder, task = self.detected.get()
            if placeholder in self.model.tasks():
                self.model.replace(placeholder, task)
                task.start()
                self.dirty = True
        self.model.refresh()
        if self.dirty:
            self.dirty = False
            self.save_session()
        self.empty.setVisible(self.model.rowCount() == 0)
        self._update_status()
        self._update_actions()
        self._update_detail()

    def _update_status(self):
        tasks = self.model.tasks()
        counts = ((sum(t.running for t in tasks), "en cours", "en cours"),
                  (sum(t.finished for t in tasks), "terminé", "terminés"),
                  (sum(bool(t.error) for t in tasks), "en erreur", "en erreur"))
        text = " · ".join(f"{n} {one if n == 1 else many}" for n, one, many in counts if n)
        self.status_left.setText(text or "Aucun téléchargement")
        total = sum(t.speed for t in tasks if t.running)
        self.status_speed.setText(f"↓ {human(total)}/s")
        now = time.monotonic()
        if now - self._last_sample >= 1:        # un point par seconde sur la courbe
            self._last_sample = now
            self.sparkline.push(total)

    def _update_detail(self):
        idx = self.table.selectionModel().currentIndex()
        sel = self.selected_tasks()
        task = None
        if sel:
            row = self.proxy.mapToSource(idx).row() if idx.isValid() else -1
            task = self.model.task(row) if 0 <= row < self.model.rowCount() and \
                self.model.task(row) in sel else sel[0]
        self.detail.show_task(task)

    # --- actions ----------------------------------------------------------------
    def selected_tasks(self):
        rows = {self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
        return [self.model.task(r) for r in sorted(rows)]

    def _update_actions(self):
        sel = self.selected_tasks()
        self.btn_resume.setEnabled(any(not t.running and not t.finished for t in sel))
        self.btn_pause.setEnabled(any(t.running for t in sel))
        self.btn_remove.setEnabled(bool(sel))

    def _selection_changed(self):
        self._update_actions()
        self._update_detail()

    def _context_menu(self, pos):
        sel = self.selected_tasks()
        if not sel:
            return
        menu = QMenu(self)
        menu.addAction(theme.icon("resume"), "Reprendre", self.resume_selected).setEnabled(
            any(not t.running and not t.finished for t in sel))
        menu.addAction(theme.icon("pause"), "Pause", self.pause_selected).setEnabled(
            any(t.running for t in sel))
        menu.addSeparator()
        menu.addAction("Ouvrir le fichier", lambda: self.open_file(sel[0])).setEnabled(sel[0].finished)
        menu.addAction(theme.icon("folder"), "Ouvrir le dossier", self.open_folder)
        menu.addAction("Copier le lien", self.copy_links)
        menu.addSeparator()
        menu.addAction(theme.icon("remove"), "Retirer de la liste", self.remove_selected)
        menu.addAction("Supprimer le fichier…", self.delete_selected_files)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _double_click(self, index):
        t = self.model.task(self.proxy.mapToSource(index).row())
        if t.finished:
            self.open_file(t)
        else:
            self.detail.setVisible(not self.detail.isVisible())

    def toggle_selected(self):
        for t in self.selected_tasks():
            if t.running:
                t.pause()
            elif not t.finished:
                t.start()

    def copy_links(self):
        QGuiApplication.clipboard().setText("\n".join(t.url for t in self.selected_tasks()))

    def open_file(self, task):
        if not task.name or not os.path.exists(task.path):
            QMessageBox.warning(self, "PyDM", "Fichier introuvable")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(task.path))

    def delete_selected_files(self):
        tasks = self.selected_tasks()
        if not tasks:
            return
        files = [f for t in tasks for f in t.files()]
        listing = "\n".join(os.path.basename(f) for f in files) or "(aucun fichier sur le disque)"
        answer = QMessageBox.question(
            self, "Supprimer le fichier",
            f"Supprimer définitivement ces fichiers et retirer {len(tasks)} ligne(s) de la liste ?\n\n{listing}")
        if answer != QMessageBox.Yes:
            return
        for t in tasks:
            t.pause()
            t.wait(5)
        errors = []
        for f in files:
            try:
                os.remove(f)
            except FileNotFoundError:
                pass
            except OSError as e:
                errors.append(f"{os.path.basename(f)} : {e.strerror}")
        self.model.remove([self.model.row_of(t) for t in tasks])
        self.save_session()
        if errors:
            QMessageBox.warning(self, "PyDM", "Certains fichiers n'ont pas pu être supprimés :\n" + "\n".join(errors))

    def resume_selected(self):
        for t in self.selected_tasks():
            t.start()

    def pause_selected(self):
        for t in self.selected_tasks():
            t.pause()

    def remove_selected(self):
        tasks = self.selected_tasks()
        for t in tasks:
            t.pause()
        self.model.remove([self.model.row_of(t) for t in tasks])
        self.save_session()

    def open_folder(self):
        sel = self.selected_tasks()
        folder = sel[0].folder if sel else os.path.expanduser(self.settings["folder"])
        if not os.path.isdir(folder):
            QMessageBox.warning(self, "PyDM", "Fichier introuvable")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def about(self):
        QMessageBox.about(self, "À propos de PyDM",
                          f"<b>PyDM {__version__}</b><br>Gestionnaire de téléchargement multi-connexions."
                          "<br>Logiciel libre sous licence GNU GPL v3 ou ultérieure.")

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        self.timer.stop()
        self._save_state()
        self.save_session()
        tasks = self.model.tasks()
        for t in tasks:
            t.pause()
        end = time.time() + 5
        for t in tasks:
            t.wait(max(0.0, end - time.time()))
        try:
            os.unlink(ipc.SOCKET_PATH)
        except OSError:
            pass
        QGuiApplication.quit()

    def closeEvent(self, event):
        self.quit_app()
        event.accept()
