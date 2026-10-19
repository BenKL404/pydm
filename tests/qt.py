"""Application Qt partagée par les tests d'interface (hors écran)."""
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"     # jamais de fenêtre sur l'écran réel
try:
    from PySide6.QtWidgets import QApplication
    HAS_QT = True
except ImportError:
    HAS_QT = False

_app = None


def app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app
