# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Interface Tkinter (provisoire, remplacée par l'interface Qt)."""
import os
import queue
import re
import shutil
import subprocess
import sys
import threading

from . import store
from .engine import (BROWSERS, QUALITIES, Download, entry_from_task, have_ytdlp, make_download,
                     task_from_entry)
from .ipc import SOCKET_PATH, start_ipc
from .util import human, human_time

def run(default_dir, parts):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("PyDM – Gestionnaire de téléchargement")
    root.geometry("980x460")
    items = {}  # iid -> Download

    url_var = tk.StringVar()
    dir_var = tk.StringVar(value=default_dir)
    parts_var = tk.IntVar(value=parts)
    clip_var = tk.BooleanVar(value=True)
    quality_var = tk.StringVar(value="Meilleure")
    browser_var = tk.StringVar(value="Aucun")
    dirty = [False]

    def add(url=None, headers=None, filename=None, kind="auto"):
        url = (url or url_var.get()).strip()
        if not re.match(r"^(https?|ftp)://", url):
            messagebox.showwarning("PyDM", "Entrez une URL http(s) ou ftp valide.")
            return
        folder, parts, quality, browser = (os.path.expanduser(dir_var.get()), parts_var.get(),
                                           quality_var.get(), browser_var.get())
        iid = tree.insert("", "end", values=("…",) * 6)
        placeholder = Download(url, folder, parts)
        placeholder.status = "Analyse…"
        items[iid] = placeholder
        url_var.set("")

        def detect():   # fichier direct ou page vidéo ? (réseau : hors du fil de l'interface)
            d = make_download(url, folder, parts, quality, browser, headers, filename, kind)
            if iid in items:
                items[iid] = d
                d.start()
                dirty[0] = True
        threading.Thread(target=detect, daemon=True).start()

    def browse():
        path = filedialog.askdirectory(initialdir=dir_var.get())
        if path:
            dir_var.set(path)

    def selected():
        return [items[i] for i in tree.selection() if i in items]

    def resume():
        for d in selected():
            d.start()

    def pause():
        for d in selected():
            d.pause()

    def remove():
        for iid in tree.selection():
            d = items.pop(iid, None)
            if d:
                d.pause()
            tree.delete(iid)
        save_session()

    def open_folder():
        sel = selected()
        folder = sel[0].folder if sel else os.path.expanduser(dir_var.get())
        subprocess.Popen(["xdg-open", folder])

    def save_session():
        store.save_session([entry_from_task(d) for d in list(items.values())])

    def load_session():
        for e in store.load_session():
            d = task_from_entry(e)
            if d.status == "En attente":
                d.status = "En pause"
            items[tree.insert("", "end", values=("…",) * 6)] = d

    inbox = queue.Queue()

    def show_window():
        root.deiconify()
        root.lift()
        root.attributes("-topmost", True)
        root.after(300, lambda: root.attributes("-topmost", False))

    def handle_inbox():     # messages envoyés par l'extension du navigateur
        while not inbox.empty():
            msg = inbox.get()
            if msg.get("action") == "add" and msg.get("url"):
                add(msg["url"], msg.get("headers"), msg.get("filename"), msg.get("kind", "auto"))
            show_window()

    def refresh():
        handle_inbox()
        if dirty[0]:
            dirty[0] = False
            save_session()
        for iid, d in list(items.items()):
            if not tree.exists(iid):
                continue
            if d.size:
                frac = d.done / d.size
                bar = "█" * int(frac * 12) + "░" * (12 - int(frac * 12))
                prog = f"{bar} {100 * frac:5.1f} %"
            else:
                prog = human(d.done)
            eta = human_time((d.size - d.done) / d.speed) if d.size and d.speed > 0 else ""
            speed = f"{human(d.speed)}/s" if d.running else ""
            tree.item(iid, values=(d.name or d.url, human(d.size), prog, speed, eta, d.status))
        root.after(500, refresh)

    last_clip = [""]

    def watch_clipboard():
        if clip_var.get():
            try:
                text = root.clipboard_get().strip()
            except tk.TclError:
                text = ""
            if text != last_clip[0]:
                last_clip[0] = text
                if re.match(r"^(https?|ftp)://\S+$", text) and not url_var.get():
                    url_var.set(text)
                    root.lift()
        root.after(1000, watch_clipboard)

    def on_close():
        save_session()
        for d in items.values():
            d.pause()
        for d in items.values():
            d.wait(5)
        try:
            os.unlink(SOCKET_PATH)
        except OSError:
            pass
        root.destroy()

    top = ttk.Frame(root, padding=8)
    top.pack(fill="x")
    ttk.Label(top, text="URL :").grid(row=0, column=0, sticky="w")
    entry = ttk.Entry(top, textvariable=url_var)
    entry.grid(row=0, column=1, columnspan=4, sticky="ew", padx=4)
    entry.bind("<Return>", lambda e: add())
    ttk.Button(top, text="Télécharger", command=add).grid(row=0, column=5, sticky="ew")
    ttk.Label(top, text="Dossier :").grid(row=1, column=0, sticky="w", pady=(6, 0))
    ttk.Entry(top, textvariable=dir_var).grid(row=1, column=1, sticky="ew", padx=4, pady=(6, 0))
    ttk.Button(top, text="…", width=3, command=browse).grid(row=1, column=2, pady=(6, 0))
    ttk.Label(top, text="Connexions :").grid(row=1, column=3, padx=(12, 2), pady=(6, 0))
    ttk.Spinbox(top, from_=1, to=32, textvariable=parts_var, width=4).grid(row=1, column=4, pady=(6, 0))
    ttk.Checkbutton(top, text="Surveiller le presse-papiers", variable=clip_var).grid(
        row=1, column=5, padx=(12, 0), pady=(6, 0))
    ttk.Label(top, text="Vidéo :").grid(row=2, column=0, sticky="w", pady=(6, 0))
    opts = ttk.Frame(top)
    opts.grid(row=2, column=1, columnspan=5, sticky="w", padx=4, pady=(6, 0))
    ttk.Combobox(opts, textvariable=quality_var, values=list(QUALITIES), state="readonly",
                 width=11).pack(side="left")
    ttk.Label(opts, text="   Cookies du navigateur :").pack(side="left")
    ttk.Combobox(opts, textvariable=browser_var, values=BROWSERS, state="readonly",
                 width=9).pack(side="left")
    info = ("yt-dlp détecté : sites de streaming pris en charge" if have_ytdlp()
            else "yt-dlp absent : pip install -U yt-dlp pour les sites de streaming")
    if have_ytdlp() and not shutil.which("ffmpeg"):
        info += " (installez ffmpeg pour la meilleure qualité)"
    ttk.Label(opts, text="   " + info, foreground="gray40").pack(side="left")
    top.columnconfigure(1, weight=1)

    cols = (("name", "Fichier", 270), ("size", "Taille", 90), ("prog", "Progression", 220),
            ("speed", "Vitesse", 100), ("eta", "Restant", 80), ("status", "Statut", 160))
    mid = ttk.Frame(root, padding=(8, 0))
    mid.pack(fill="both", expand=True)
    tree = ttk.Treeview(mid, columns=[c[0] for c in cols], show="headings")
    for key, title, width in cols:
        tree.heading(key, text=title)
        tree.column(key, width=width, anchor="w")
    sb = ttk.Scrollbar(mid, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    bottom = ttk.Frame(root, padding=8)
    bottom.pack(fill="x")
    for text, cmd in (("▶ Reprendre", resume), ("⏸ Pause", pause), ("✖ Retirer", remove),
                      ("📂 Ouvrir le dossier", open_folder)):
        ttk.Button(bottom, text=text, command=cmd).pack(side="left", padx=(0, 6))

    load_session()
    try:
        start_ipc(lambda msg: inbox.put(msg) or {"ok": True})
    except OSError as e:
        print(f"Extension du navigateur indisponible : {e}", file=sys.stderr)
    root.protocol("WM_DELETE_WINDOW", on_close)
    refresh()
    watch_clipboard()
    entry.focus()
    root.mainloop()
