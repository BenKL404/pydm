# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""PyDM - gestionnaire de téléchargement multi-connexions (style IDM) pour Linux.

  Interface graphique :  python3 -m pydm
  Ligne de commande   :  python3 -m pydm URL [-o DOSSIER] [-n CONNEXIONS] [-q QUALITE]

Fonctions : téléchargement découpé en plusieurs connexions parallèles,
découpage dynamique (une connexion libre reprend la moitié du plus gros
segment restant), pause / reprise même après fermeture, relance automatique
en cas de coupure, surveillance du presse-papiers.
Vidéos des sites de streaming (YouTube, Vimeo, Twitch, Dailymotion, TikTok,
flux HLS/DASH…) via yt-dlp s'il est installé : pip install -U yt-dlp
(ffmpeg recommandé pour la meilleure qualité et le MP3).
Aucune autre dépendance hors bibliothèque standard (Tkinter pour l'interface).
"""
import argparse
import os
import sys
import time

from .engine import BROWSERS, QUALITIES, Download, make_download
from .ipc import instance_running
from .util import human, human_time


def run_cli(url, folder, parts, quality="Meilleure", browser="Aucun"):
    d = make_download(url, folder, parts, quality, browser)
    d.start()
    try:
        while d.running:
            time.sleep(0.5)
            pct = f"{100 * d.done / d.size:5.1f} %" if d.size else ""
            eta = human_time((d.size - d.done) / d.speed) if d.size and d.speed else ""
            if isinstance(d, Download):
                extra = f"[{sum(1 for s in d.segments if s[1] < 0 or Download._remaining(s) > 0)} conn.]"
            else:
                extra = d.status
            sys.stdout.write(f"\r{(d.name or '')[:50]}  {pct}  {human(d.done)}/{human(d.size)}  "
                             f"{human(d.speed)}/s  {eta}  {extra}   ")
            sys.stdout.flush()
    except KeyboardInterrupt:
        d.pause()
        d.wait()
    print(f"\n{d.status}" + (f" -> {d.path}" if d.finished else ""))
    if d.status == "En pause":
        print("Relancez la même commande pour reprendre.")
    return 0 if d.finished else 1


def default_folder():
    fr = os.path.expanduser("~/Téléchargements")
    return fr if os.path.isdir(fr) else os.path.expanduser("~/Downloads")


def main(argv=None):
    p = argparse.ArgumentParser(prog="pydm", description="PyDM - téléchargements multi-connexions")
    p.add_argument("url", nargs="?", help="URL à télécharger (sans URL : interface graphique)")
    p.add_argument("-o", "--output", default=default_folder(), help="dossier de destination")
    p.add_argument("-n", "--connections", type=int, default=8, help="nombre de connexions (défaut 8)")
    p.add_argument("-q", "--qualite", default="Meilleure", choices=list(QUALITIES),
                   help="qualité pour les vidéos de streaming")
    p.add_argument("--cookies", default="Aucun", choices=BROWSERS,
                   help="utiliser les cookies de ce navigateur (vidéos nécessitant votre compte)")
    a = p.parse_args(argv)
    if a.url:
        sys.exit(run_cli(a.url, a.output, a.connections, a.qualite, a.cookies))
    if instance_running():      # déjà ouvert : on affiche la fenêtre existante
        return
    try:
        import tkinter  # noqa: F401
    except ImportError:
        sys.exit("Tkinter manquant : sudo apt install python3-tk   (ou dnf install python3-tkinter)")
    from . import tkgui
    tkgui.run(a.output, a.connections)
