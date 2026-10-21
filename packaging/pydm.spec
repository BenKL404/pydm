# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
# Configuration PyInstaller : PyDM figé en un dossier (Python, Qt, yt-dlp, ffmpeg).
# Commune à Linux (AppImage) et, plus tard, Windows.
# Variable PYDM_FFMPEG_DIR : dossier contenant ffmpeg et ffprobe, livrés dans le dossier des binaires (_internal).
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.dirname(SPECPATH)            # noqa: F821 (fourni par PyInstaller)
SUFFIX = ".exe" if sys.platform == "win32" else ""
FFMPEG_DIR = os.environ.get("PYDM_FFMPEG_DIR")

binaries = [(os.path.join(FFMPEG_DIR, name + SUFFIX), ".") for name in ("ffmpeg", "ffprobe")] if FFMPEG_DIR else []

# modules Qt jamais utilisés : PyDM n'emploie que QtCore, QtGui, QtWidgets et QtSvg
UNUSED_QT = ["Qt3DAnimation", "Qt3DCore", "Qt3DExtras", "Qt3DInput", "Qt3DLogic", "Qt3DRender", "QtBluetooth",
             "QtCharts", "QtConcurrent", "QtDataVisualization", "QtDesigner", "QtGraphs", "QtHelp",
             "QtHttpServer", "QtLocation", "QtMultimedia", "QtMultimediaWidgets", "QtNetworkAuth", "QtNfc",
             "QtOpenGL", "QtOpenGLWidgets", "QtPdf", "QtPdfWidgets", "QtPositioning", "QtQml", "QtQuick",
             "QtQuick3D", "QtQuickControls2", "QtQuickWidgets", "QtRemoteObjects", "QtScxml", "QtSensors",
             "QtSerialBus", "QtSerialPort", "QtSpatialAudio", "QtSql", "QtStateMachine", "QtSvgWidgets",
             "QtTest", "QtTextToSpeech", "QtUiTools", "QtWebChannel", "QtWebEngineCore", "QtWebEngineQuick",
             "QtWebEngineWidgets", "QtWebSockets", "QtWebView", "QtXml"]

a = Analysis(                               # noqa: F821
    [os.path.join(ROOT, "pydm", "__main__.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=[(os.path.join(ROOT, "pydm", "gui", "icons"), os.path.join("pydm", "gui", "icons")),
           (os.path.join(ROOT, "pydm.desktop"), ".")],
    hiddenimports=["pydm_host"] + collect_submodules("pydm") + collect_submodules("yt_dlp"),
    excludes=["tkinter"] + [f"PySide6.{m}" for m in UNUSED_QT],
)
pyz = PYZ(a.pure)                           # noqa: F821
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="pydm", console=False,  # noqa: F821
          icon=os.path.join(ROOT, "pydm", "gui", "icons", "png", "pydm-256.png"))
coll = COLLECT(exe, a.binaries, a.datas, name="pydm")    # noqa: F821
