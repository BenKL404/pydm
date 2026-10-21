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
Moteur et ligne de commande : bibliothèque standard uniquement ; interface : PySide6 (Qt 6).
"""
import argparse
import os
import sys
import time

from . import store
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


def connections(value):
    n = int(value)
    if not 1 <= n <= 32:
        raise argparse.ArgumentTypeError("le nombre de connexions doit être entre 1 et 32")
    return n


def folder(value):
    return os.path.abspath(os.path.expanduser(value))


def prepare_frozen_env(environ, executable):
    """Programme figé : ffmpeg livré à côté de l'exécutable, et bibliothèques du système pour les
    programmes lancés (navigateur, gestionnaire de fichiers…) au lieu de celles du paquet."""
    environ["PATH"] = os.pathsep.join(p for p in (os.path.dirname(executable), environ.get("PATH")) if p)
    original = environ.pop("LD_LIBRARY_PATH_ORIG", None)
    if original:
        environ["LD_LIBRARY_PATH"] = original
    else:
        environ.pop("LD_LIBRARY_PATH", None)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if getattr(sys, "frozen", False):
        prepare_frozen_env(os.environ, sys.executable)
    if argv[:1] == ["--native-host"]:       # lancé par le navigateur, qui ajoute ses propres arguments
        import pydm_host
        pydm_host.main()
        return
    p = argparse.ArgumentParser(prog="pydm", description="PyDM - téléchargements multi-connexions")
    p.add_argument("url", nargs="?", help="URL à télécharger (sans URL : interface graphique)")
    p.add_argument("-o", "--output", type=folder, help="dossier de destination (défaut : celui des préférences)")
    p.add_argument("-n", "--connections", type=connections, help="nombre de connexions (défaut : préférences, 8)")
    p.add_argument("-q", "--qualite", default="Meilleure", choices=list(QUALITIES),
                   help="qualité pour les vidéos de streaming")
    p.add_argument("--cookies", default="Aucun", choices=BROWSERS,
                   help="utiliser les cookies de ce navigateur (vidéos nécessitant votre compte)")
    p.add_argument("--minimized", action="store_true", help="démarrer réduit dans la barre système")
    a = p.parse_args(argv)
    settings = store.load_settings()
    if a.url:
        sys.exit(run_cli(a.url, a.output or os.path.expanduser(settings["folder"]), a.connections or settings["parts"],
                         a.qualite, a.cookies))
    if instance_running():      # déjà ouvert : on affiche la fenêtre existante
        return
    try:
        from .gui import app
    except ImportError:
        sys.exit("Interface indisponible : PySide6 n'est pas installé. Relancez ./install.sh")
    sys.exit(app.run(settings, a.output, a.connections, a.minimized))
