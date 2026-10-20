# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Fenêtre principale : barre d'en-tête, tableau des téléchargements, barre d'état."""
import os
import queue
import threading
import time
from datetime import datetime

from PySide6.QtCore import QByteArray, QEvent, QItemSelection, QItemSelectionModel, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMenu, QMessageBox, QPushButton, QSplitter, QTableView,
                               QToolButton, QVBoxLayout, QWidget)

from .. import __version__, ipc, store
from ..analyze import analyze
from ..cache import AnalysisCache
from ..scheduler import LIMITER, Scheduler, parse_hhmm
from ..filetypes import _BY_EXT
from ..util import human, unique_path

MEDIA_EXTS = {ext for ext, cat in _BY_EXT.items() if cat in ("video", "music")}


def video_stem(name):
    """Nom choisi pour une vidéo, sans son extension (None : nom donné par le titre)."""
    n = (name or "").strip()
    stem, ext = os.path.splitext(n)
    if ext[1:].lower() in MEDIA_EXTS:
        n = stem.strip()
    if not n or (n.startswith(".") and n[1:].lower() in MEDIA_EXTS):
        return None
    return n
from ..engine import BROWSERS, QUALITIES, Download, entry_from_task, make_download, task_from_entry
from . import theme
from .adddialog import AddDialog
from .delegates import ProgressDelegate
from .links import extract_urls
from .model import DownloadFilter, DownloadModel, counts
from .schedule import EndActionDialog, ScheduleDialog, run_end_action
from .sidebar import Sidebar
from .widgets import DetailPanel, SpeedSparkline

WIDTHS = (300, 80, 190, 90, 80, 170, 120)


class MainWindow(QMainWindow):
    def __init__(self, settings, factory=make_download, overrides=None, analyzer=analyze):
        super().__init__()
        self.settings = settings
        self.analyzer = analyzer
        self.cache = AnalysisCache(analyzer=analyzer)      # analyses anticipées et récentes
        self.dialogs = []               # fenêtres d'ajout ouvertes
        self._placeholders = set()      # lignes « Analyse… » en attente de la tâche réelle
        self.scheduler = Scheduler()
        self.clock = datetime.now       # remplaçable dans les tests
        self.end_delay = 60             # secondes avant l'action finale
        self.end_dialog = None          # compte à rebours en cours
        self._end_errors = queue.Queue()    # résultats de systemctl (thread)
        self.overrides = dict(overrides or {})     # options -o / -n : pour cette session seulement
        self.factory = factory
        self.inbox = queue.Queue()      # messages de l'extension (thread IPC)
        self.detected = queue.Queue()   # (ligne provisoire, tâche) issus des threads de détection
        self.dirty = False
        self.tray = None                # barre système, créée par app.run si disponible
        self._seen = {}                 # id(tâche) -> (terminée, erreur) au dernier passage
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
        self.sidebar = Sidebar()
        self.sidebar.filter_changed.connect(self._filter_changed)
        self.sidebar.folder_requested.connect(self.open_category_folder)
        self.sidebar.setVisible(self.settings["sidebar"])
        self.hsplit = QSplitter(Qt.Horizontal)
        self.hsplit.addWidget(self.sidebar)
        self.hsplit.addWidget(self.vsplit)
        self.hsplit.setStretchFactor(1, 1)
        self.hsplit.setCollapsible(1, False)
        self.hsplit.setSizes([180, 920])
        lay.addWidget(self.hsplit, 1)
        self.setCentralWidget(central)
        self.status_left = QLabel()
        self.status_left.setContentsMargins(8, 0, 0, 0)
        self.statusBar().addWidget(self.status_left, 1)
        self.sparkline = SpeedSparkline()
        self.status_speed = QLabel()
        self.status_speed.setContentsMargins(0, 0, 8, 0)
        self.limit_btn = QToolButton()
        self.limit_btn.setCheckable(True)
        self.limit_btn.setToolTip("Limiter la vitesse totale (réglage dans Planification…)")
        self.limit_btn.clicked.connect(self.toggle_limit)
        self.statusBar().addPermanentWidget(self.limit_btn)
        self.statusBar().addPermanentWidget(self.sparkline)
        self.apply_queue_settings()
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
        self.btn_force = self._tool("force", "Forcer (démarrer tout de suite)", self.force_selected)
        self.btn_schedule = self._tool("schedule", "Planifier", lambda: None)
        self.schedule_menu = QMenu(self)
        self.schedule_menu.addAction(theme.icon("resume"), "Démarrer la file", self.start_queue)
        self.schedule_menu.addAction(theme.icon("pause"), "Arrêter la file", self.stop_queue)
        self.schedule_menu.addSeparator()
        self.schedule_menu.addAction(theme.icon("schedule"), "Planification…", self.open_schedule)
        self.btn_schedule.setMenu(self.schedule_menu)
        self.btn_schedule.setPopupMode(QToolButton.InstantPopup)
        for b in (self.btn_resume, self.btn_pause, self.btn_force, self.btn_remove, self.btn_folder,
                  self.btn_schedule):
            h.addWidget(b)
        h.addSpacing(8)
        self.btn_search = self._tool("search", "Rechercher", self.toggle_search, "Ctrl+F")
        h.addWidget(self.btn_search)
        self.btn_menu = self._tool("menu", "Menu", lambda: None)
        self.menu = QMenu(self)
        self.menu.addAction("Préférences…\tCtrl+,", self.open_preferences)
        self.sidebar_action = self.menu.addAction("Barre latérale\tCtrl+B", self.toggle_sidebar)
        self.sidebar_action.setCheckable(True)
        self.sidebar_action.setChecked(self.settings["sidebar"])
        self.menu.addAction("À propos de PyDM", self.about)
        self.menu.addSeparator()
        self.menu.addAction("Quitter\tCtrl+Q", self.quit_app)
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
                           ("Ctrl+,", self.open_preferences), ("Ctrl+B", self.toggle_sidebar),
                           ("Ctrl+Q", self.quit_app)):
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
            if mods == Qt.ControlModifier and key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Home):
                self.move_selected_top() if key == Qt.Key_Home else self.move_selected(-1 if key == Qt.Key_Up else 1)
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
        if mime.hasUrls():      # les navigateurs fournissent aussi le texte : on ne garde que les liens
            text = "\n".join(u.toString(QUrl.FullyEncoded) for u in mime.urls())
        else:
            text = mime.text()
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
                             ("splitter", self.vsplit.restoreState),
                             ("hsplit", self.hsplit.restoreState)):
            if w.get(key):
                restore(QByteArray.fromBase64(w[key].encode()))

    def _save_state(self):
        self.settings["window"] = {
            "geometry": bytes(self.saveGeometry().toBase64()).decode(),
            "header": bytes(self.table.horizontalHeader().saveState().toBase64()).decode(),
            "splitter": bytes(self.vsplit.saveState().toBase64()).decode(),
            "hsplit": bytes(self.hsplit.saveState().toBase64()).decode(),
        }
        store.save_settings(self.settings)

    # --- session ---------------------------------------------------------------
    def _load_session(self):
        for e in store.load_session():
            if not (isinstance(e, dict) and isinstance(e.get("url"), str) and isinstance(e.get("folder"), str)):
                continue        # entrée abîmée : ignorée plutôt que d'empêcher le démarrage
            try:
                t = task_from_entry(e)
            except (KeyError, TypeError, ValueError, AttributeError):
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

    def add_urls(self, urls, headers=None, filename=None, kind="auto", title=None):
        if self.end_dialog:             # de nouveaux téléchargements : on n'éteint plus
            self.end_dialog.reject()
            self.statusBar().showMessage("Action de fin de file annulée : nouveau téléchargement", 8000)
        if self.settings["confirm_add"]:
            self._open_add_dialog(urls, headers, filename, kind, title)
            return
        opts = {**self.settings, **self.overrides}
        for url in urls:
            self._enqueue(url, os.path.expanduser(opts["folder"]), opts["parts"], opts["quality"],
                          opts["browser"], headers, filename, kind, route=self._route(opts))

    @staticmethod
    def _route(opts, base=None):
        """Catégorie → dossier de rangement (sous le dossier principal, ou `base`)."""
        settings = {**opts, "folder": base or opts["folder"]}
        return lambda cat: store.folder_for(cat, settings)

    def _filter_changed(self, state, kind):
        self.proxy.set_state(state)
        self.proxy.set_type(kind)
        self._update_empty()

    def _update_empty(self):
        if self.model.rowCount() == 0:
            self.empty.setText("Collez un lien ou glissez-le ici pour commencer")
        else:
            self.empty.setText("Aucun téléchargement dans cette vue")
        self.empty.setVisible(self.proxy.rowCount() == 0)

    def toggle_sidebar(self):
        visible = self.sidebar.isHidden()
        self.sidebar.setVisible(visible)
        self.sidebar_action.setChecked(visible)
        self._set("sidebar", visible)

    def open_category_folder(self, category):
        folder = store.folder_for(category, {**self.settings, **self.overrides})
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            QMessageBox.warning(self, "PyDM", f"Dossier inutilisable : {folder}\n{e.strerror}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def apply_queue_settings(self):
        """Simultanés, plage horaire et limite de vitesse d'après les réglages."""
        s = self.settings
        self.scheduler.max_active = s["max_active"]
        self.scheduler.window = ((parse_hhmm(s["schedule_start"]), parse_hhmm(s["schedule_end"]))
                                 if s["schedule_on"] else None)
        LIMITER.rate = s["speed_kbps"] * 1024 if s["speed_on"] else 0
        self.limit_btn.setText(f"Limite {human(s['speed_kbps'] * 1024)}/s")
        self.limit_btn.setChecked(s["speed_on"])

    def toggle_limit(self):
        self._set("speed_on", not self.settings["speed_on"])
        self.apply_queue_settings()

    def start_queue(self):
        self.scheduler.start_queue()
        self.tick()

    def stop_queue(self):
        self.scheduler.stop_queue()
        self.tick()

    def open_schedule(self):
        dlg = ScheduleDialog(self.settings, self)
        if dlg.exec() != ScheduleDialog.Accepted:
            return
        self.settings.update(dlg.result_settings())
        store.save_settings(self.settings)
        self.apply_queue_settings()
        self.tick()

    def queue_finished(self):
        """La file planifiée est terminée : action finale choisie dans Planification."""
        action = self.settings["end_action"]
        if action == "none":
            return
        if self.end_dialog:
            return
        if self.end_delay <= 0:
            self._end_action(action)
            return
        dlg = EndActionDialog(action, self.end_delay, self)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        self.end_dialog = dlg
        dlg.finished.connect(lambda *_: setattr(self, "end_dialog", None))
        dlg.confirmed.connect(lambda: self._end_action(action))
        dlg.show()
        dlg.raise_()
        if self.tray and not self.isVisible():
            self.tray.notify("La file est terminée", dlg.label.text(), on_click=dlg.raise_)

    def _end_action(self, action):
        if action == "quit":
            self.quit_app()
            return
        self.save_session()
        threading.Thread(target=lambda: self._end_errors.put(run_end_action(action)), daemon=True).start()

    def _enqueue(self, url, folder, parts, quality, browser, headers, filename, kind,
                 fmt=None, stem=None, want="now", route=None):
        placeholder = Download(url, folder, parts)
        placeholder.status = "Analyse…"
        placeholder.want = "stop"       # la file ne démarre pas la ligne provisoire
        self._placeholders.add(placeholder)
        self.model.add(placeholder)

        def detect():   # réseau : hors du thread de l'interface
            try:
                task = self.factory(url, folder, parts, quality, browser, headers, filename, kind,
                                    fmt=fmt, stem=stem, route=route)
            except Exception as e:  # noqa: BLE001
                placeholder.error = str(e)
                placeholder.status = f"Erreur : {e}"
                return
            self.detected.put((placeholder, task, want))
        threading.Thread(target=detect, daemon=True).start()
        self._update_actions()

    def _open_add_dialog(self, urls, headers, filename, kind, title=None):
        dlg = AddDialog(self.settings, urls, headers, filename, kind, parent=self, analyzer=self.cache.get,
                        title=title)
        if self.overrides.get("folder"):
            dlg.folder_edit.setText(self.overrides["folder"])
        dlg.accepted_tasks.connect(self._accept)
        dlg.finished.connect(lambda *_: dlg in self.dialogs and self.dialogs.remove(dlg))
        self.dialogs.append(dlg)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        QTimer.singleShot(500, lambda: self._check_front(dlg))

    def _check_front(self, dlg):
        """Sous Wayland, une fenêtre peut rester derrière le navigateur : on le signale."""
        if dlg in self.dialogs and dlg.isVisible() and not dlg.isActiveWindow() and self.tray:
            def bring():
                if dlg in self.dialogs:
                    dlg.show()
                    dlg.raise_()
                    dlg.activateWindow()
            self.tray.notify("Choisissez la qualité dans PyDM", dlg.windowTitle(), on_click=bring)

    def _accept(self, entries, start):
        opts = {**self.settings, **self.overrides}
        for e in entries:
            folder = os.path.expanduser(e["folder"])
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError as err:
                QMessageBox.warning(self, "PyDM", f"Dossier inutilisable : {folder}\n{err.strerror}")
                return
            stem, filename = None, e.get("filename")
            if e["kind"] == "video":       # même titre déjà présent : « titre (1) »
                stem = video_stem(unique_path(folder, e["name"])) if e.get("name") else None
            elif e.get("name"):
                filename = e["name"]
            route = self._route(opts, folder) if e.get("auto_folder") else None    # type encore inconnu
            self._enqueue(e["url"], folder, opts["parts"], e["quality"], opts["browser"], e.get("headers"),
                          filename, e["kind"], fmt=e.get("fmt"), stem=stem,
                          want="now" if start else "later", route=route)

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
            if msg.get("action") == "prefetch" and msg.get("url"):
                self.cache.prefetch(msg["url"], msg.get("headers"), self.settings["browser"])
                continue            # préparation silencieuse : ni fenêtre ni premier plan
            if msg.get("action") == "add" and msg.get("url"):
                self.add_urls([msg["url"]], msg.get("headers"), msg.get("filename"), msg.get("kind", "auto"),
                              msg.get("title"))
                if self.settings["confirm_add"]:
                    continue        # la fenêtre d'ajout passe devant ; la principale reste où elle est
            self.show_window()
        while not self.detected.empty():
            placeholder, task, want = self.detected.get()
            self._placeholders.discard(placeholder)
            if placeholder in self.model.tasks():
                self.model.replace(placeholder, task)
                # la file la démarre (ou l'attend) ; une pause demandée pendant l'analyse est gardée
                task.want = "stop" if getattr(placeholder, "user_stop", False) else want
                self.dirty = True
        while not self._end_errors.empty():
            error = self._end_errors.get()
            if error:
                QMessageBox.warning(self, "PyDM", error)
        if self.scheduler.tick(self.model.tasks(), self.clock()):
            self.queue_finished()
        self.model.refresh()
        self._notify_transitions()
        if self.dirty:
            self.dirty = False
            self.save_session()
        self.proxy.refilter()
        self.sidebar.update_counts(*counts(self.model.tasks()))
        self._update_empty()
        self._update_status()
        self._update_actions()
        self._update_detail()

    def _update_status(self):
        tasks = self.model.tasks()
        counts = ((sum(t.running for t in tasks), "en cours", "en cours"),
                  (sum(t.finished for t in tasks), "terminé", "terminés"),
                  (sum(bool(t.error) for t in tasks), "en erreur", "en erreur"))
        queued = sum(1 for t in tasks if t.want in ("now", "later") and not t.running
                     and not t.finished and not t.error)
        counts = counts[:1] + ((queued, "en file", "en file"),) + counts[1:]
        parts = [f"{n} {one if n == 1 else many}" for n, one, many in counts if n]
        sch, now = self.scheduler, self.clock()
        if sch.window:
            plage = f"plage {sch.window[0]:%H:%M}–{sch.window[1]:%H:%M}"
            if not sch.queue_active(now):
                plage += f" (reprise à {sch.next_start(now):%H:%M})"
            parts.append(plage)
        if sch.queue_started:
            parts.append("file démarrée")
        self.status_left.setText(" · ".join(parts) or "Aucun téléchargement")
        total = sum(t.speed for t in tasks if t.running)
        self.status_speed.setText(f"↓ {human(total)}/s")
        now = time.monotonic()
        if now - self._last_sample >= 1:        # un point par seconde sur la courbe
            self._last_sample = now
            self.sparkline.push(total)
        if self.tray:
            self.tray.update(sum(t.running for t in tasks), total)

    def _notify_transitions(self):
        seen = {}
        for t in self.model.tasks():
            now = (t.finished, bool(t.error))
            before = self._seen.get(id(t))
            seen[id(t)] = now
            if before is None or not (self.tray and self.settings["notify"]):
                continue            # première apparition (session, ajout) : rien à signaler
            name = t.name or t.url
            if now[0] and not before[0]:
                self.tray.notify("Téléchargement terminé", name, t.folder)
            elif now[1] and not before[1]:
                self.tray.notify("Échec", f"{name} : {t.error[:80]}")
        self._seen = seen

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
        if sel:
            self.build_context_menu(sel).exec(self.table.viewport().mapToGlobal(pos))

    def build_context_menu(self, sel):
        menu = QMenu(self)
        menu.addAction(theme.icon("resume"), "Reprendre", self.resume_selected).setEnabled(
            any(not t.running and not t.finished for t in sel))
        menu.addAction(theme.icon("pause"), "Pause", self.pause_selected).setEnabled(
            any((t.running or t.want != "stop") and not t.finished for t in sel))
        menu.addAction(theme.icon("force"), "Forcer", self.force_selected)
        menu.addAction(theme.icon("schedule"), "Mettre dans la file", self.queue_selected)
        menu.addSeparator()
        menu.addAction("Monter\tCtrl+↑", lambda: self.move_selected(-1))
        menu.addAction("Descendre\tCtrl+↓", lambda: self.move_selected(1))
        menu.addAction("En tête de file\tCtrl+Origine", self.move_selected_top)
        menu.addSeparator()
        menu.addAction("Ouvrir le fichier", lambda: self.open_file(sel[0])).setEnabled(sel[0].finished)
        menu.addAction(theme.icon("folder"), "Ouvrir le dossier", self.open_folder)
        menu.addAction("Copier le lien", self.copy_links)
        menu.addSeparator()
        menu.addAction(theme.icon("remove"), "Retirer de la liste", self.remove_selected)
        menu.addAction("Supprimer le fichier…", self.delete_selected_files)
        return menu

    def _double_click(self, index):
        t = self.model.task(self.proxy.mapToSource(index).row())
        if t.finished:
            self.open_file(t)
        else:
            self.detail.setVisible(not self.detail.isVisible())

    def _set_want(self, t, want):
        """Change l'état voulu à la demande de l'utilisateur (relance une tâche en erreur)."""
        if t.finished or t in self._placeholders:
            return
        t.error = None
        t.want = want

    def toggle_selected(self):
        for t in self.selected_tasks():
            if t.running or t.want in ("now", "later", "force"):
                self._stop(t)
            else:
                self._set_want(t, "now")
        self.dirty = True

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
        end = time.time() + 5
        for t in tasks:
            t.wait(max(0.0, end - time.time()))
        files = [f for t in tasks for f in t.files()]       # l'état est écrit à la pause
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

    def pause_all(self):
        for t in self.model.tasks():
            self._stop(t)
        self.dirty = True

    def resume_all(self):
        for t in self.model.tasks():
            if t.want != "now":
                self._set_want(t, "now")
        self.dirty = True

    def open_preferences(self):
        from .prefs import PreferencesDialog, set_autostart
        dlg = PreferencesDialog(self.settings, self.tray is not None, self)
        if dlg.exec() != PreferencesDialog.Accepted:
            return
        new = dlg.result_settings()
        if new["autostart"] != self.settings["autostart"]:
            try:
                set_autostart(new["autostart"])
            except OSError as e:
                QMessageBox.warning(self, "PyDM", f"Démarrage avec la session impossible : {e.strerror}")
                new["autostart"] = self.settings["autostart"]
        theme_changed = new["theme"] != self.settings["theme"]
        self.settings.update(new)
        store.save_settings(self.settings)
        if theme_changed:
            theme.apply(QGuiApplication.instance(), new["theme"])
            self.refresh_icons()

    def refresh_icons(self):
        """Recolore les icônes après un changement de thème."""
        for b in self.findChildren(QToolButton):
            name = b.property("icon_name")
            if name:
                b.setIcon(theme.icon(name))
        self.empty.setStyleSheet(f"color: {theme.colors()['muted']}; font-size: 14px;")
        self.model.layoutChanged.emit()
        self._update_detail()

    def force_selected(self):
        for t in self.selected_tasks():
            self._set_want(t, "force")
        self.dirty = True
        self.tick()

    def queue_selected(self):
        for t in self.selected_tasks():
            self._set_want(t, "later")
        self.dirty = True
        self.tick()

    def _unsort(self):
        self.proxy.sort(-1)                         # l'ordre de la liste devient celui de la file
        self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)

    def _reselect(self, tasks):
        sel = QItemSelection()
        for t in tasks:
            idx = self.proxy.mapFromSource(self.model.index(self.model.row_of(t), 0))
            sel.select(idx, idx)
        self.table.selectionModel().select(sel, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        if tasks:
            first = self.proxy.mapFromSource(self.model.index(self.model.row_of(tasks[0]), 0))
            self.table.selectionModel().setCurrentIndex(first, QItemSelectionModel.NoUpdate)
        self.dirty = True

    def move_selected(self, delta):
        """Échange avec la ligne visible voisine (filtres et recherche respectés)."""
        tasks = self.selected_tasks()
        if not tasks:
            return
        self._unsort()
        for t in (tasks if delta < 0 else reversed(tasks)):
            pr = self.proxy.mapFromSource(self.model.index(self.model.row_of(t), 0)).row() + delta
            if not 0 <= pr < self.proxy.rowCount():
                continue
            other = self.model.task(self.proxy.mapToSource(self.proxy.index(pr, 0)).row())
            if other not in tasks:
                self.model.swap(self.model.row_of(t), self.model.row_of(other))
        self._reselect(tasks)

    def move_selected_top(self):
        tasks = self.selected_tasks()
        if not tasks:
            return
        self._unsort()
        self.model.move_to_top([self.model.row_of(t) for t in tasks])
        self._reselect(tasks)

    def resume_selected(self):
        for t in self.selected_tasks():
            self._set_want(t, "now")
        self.dirty = True

    def _stop(self, t):
        if t in self._placeholders:
            t.user_stop = True
        t.want = "stop"
        t.pause()
        if not t.running and not t.finished and not t.error:
            t.status = "En pause"

    def pause_selected(self):
        for t in self.selected_tasks():
            self._stop(t)
        self.dirty = True

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
        if self.tray and self.settings["close_to_tray"]:
            event.ignore()
            self.hide()
            if not self.settings["tray_hint_shown"]:
                self.tray.notify("PyDM continue en arrière-plan",
                                 "Les téléchargements se poursuivent. Quittez depuis l'icône de la barre système.")
                self._set("tray_hint_shown", True)
            return
        self.quit_app()
        event.accept()
