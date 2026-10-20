# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Thème clair / sombre, icônes SVG recolorées et logo de PyDM."""
import os

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
TYPE_COLORS = {"video": "#a78bfa", "music": "#f472b6", "document": "#60a5fa", "image": "#fb923c",
               "archive": "#fbbf24", "program": "#34d399", "other": "#94a3b8"}
STATE_COLORS = {"done": "#22c55e", "paused": "#eab308", "error": "#ef4444"}
SIZES = (16, 20, 24, 32, 48, 64, 128, 256)

DARK = {"window": "#1b1d22", "base": "#16181c", "alt": "#1d2025", "button": "#22252b",
        "text": "#e6e8ec", "muted": "#8b929c", "border": "#2c3038", "accent": "#22d3ee",
        "select": "#164e63", "select_text": "#ffffff"}
LIGHT = {"window": "#f4f5f7", "base": "#ffffff", "alt": "#f7f8fa", "button": "#eceef1",
         "text": "#111827", "muted": "#6b7280", "border": "#d8dce2", "accent": "#0891b2",
         "select": "#cff4fc", "select_text": "#0f172a"}

_state = {"dark": False, "mode": "system", "colors": LIGHT}
_cache = {}


def is_dark():
    return _state["dark"]


def colors():
    return _state["colors"]


def accent():
    return QColor(colors()["accent"])


def _svg(name, color=None):
    with open(os.path.join(ICONS_DIR, name + ".svg"), encoding="utf-8") as f:
        text = f.read()
    if color:
        text = text.replace("currentColor", color)
    return QSvgRenderer(QByteArray(text.encode()))


def _icon(renderer):
    icon = QIcon()
    for size in SIZES:
        for dpr in (1, 2):
            img = QImage(size * dpr, size * dpr, QImage.Format_ARGB32_Premultiplied)
            img.fill(Qt.transparent)
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing)
            renderer.render(p, QRectF(0, 0, size * dpr, size * dpr))
            p.end()
            pix = QPixmap.fromImage(img)
            pix.setDevicePixelRatio(dpr)
            icon.addPixmap(pix)
    return icon


def icon(name, color=None):
    """Icône de l'interface ; le glyphe prend `color` (par défaut la couleur du texte du thème)."""
    color = color or colors()["text"]
    key = (name, color)
    if key not in _cache:
        _cache[key] = _icon(_svg(name, color))
    return _cache[key]


def type_icon(category):
    return icon("type-" + category, TYPE_COLORS.get(category, TYPE_COLORS["other"]))


def logo():
    if "logo" not in _cache:
        _cache["logo"] = _icon(_svg("logo"))
    return _cache["logo"]


def _palette(c):
    pal = QPalette()
    roles = {QPalette.Window: "window", QPalette.Base: "base", QPalette.AlternateBase: "alt",
             QPalette.Button: "button", QPalette.WindowText: "text", QPalette.Text: "text",
             QPalette.ButtonText: "text", QPalette.ToolTipBase: "button", QPalette.ToolTipText: "text",
             QPalette.Highlight: "select", QPalette.HighlightedText: "select_text",
             QPalette.PlaceholderText: "muted", QPalette.Link: "accent", QPalette.Accent: "accent"}
    for role, key in roles.items():
        pal.setColor(role, QColor(c[key]))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(c["muted"]))
    return pal


STYLE = """
QToolButton {{ border: none; border-radius: 6px; padding: 5px; }}
QToolButton:hover {{ background: {border}; }}
QToolButton:disabled {{ background: transparent; }}
QToolButton:checked {{ background: {select}; color: {select_text}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QFrame#header {{ border-bottom: 1px solid {border}; }}
QLineEdit, QComboBox {{ border: 1px solid {border}; border-radius: 6px; padding: 5px 8px;
    background: {base}; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {accent}; }}
QPushButton#primary {{ background: {accent}; color: {on_accent}; border: none; border-radius: 6px;
    padding: 6px 14px; font-weight: 600; }}
QPushButton#primary:hover {{ background: {accent_hover}; }}
QTableView {{ border: none; gridline-color: transparent; selection-background-color: {select};
    selection-color: {select_text}; }}
QHeaderView::section {{ background: {window}; color: {muted}; border: none;
    border-bottom: 1px solid {border}; padding: 5px 8px; }}
QSplitter::handle {{ background: {border}; }}
QTableView::indicator {{ width: 14px; height: 14px; border: 1px solid {muted};
    border-radius: 3px; background: {base}; }}
QTableView::indicator:checked {{ background: {accent}; border-color: {accent}; }}
QStatusBar {{ color: {muted}; padding-left: 8px; }}
QStatusBar::item {{ border: none; }}
QToolTip {{ border: 1px solid {border}; border-radius: 4px; padding: 4px 6px; }}
"""


def apply(app, mode="system"):
    """Applique le style Fusion avec la palette claire ou sombre (`mode` : system, light, dark)."""
    _state["mode"] = mode
    if mode == "system":
        dark = app.styleHints().colorScheme() == Qt.ColorScheme.Dark     # suivi : MainWindow
    else:
        dark = mode == "dark"
    c = DARK if dark else LIGHT
    _state.update(dark=dark, colors=c)
    _cache.clear()
    app.setStyle("Fusion")
    app.setPalette(_palette(c))
    accent_hover = QColor(c["accent"]).lighter(115 if dark else 90).name()
    app.setStyleSheet(STYLE.format(on_accent="#0f172a" if dark else "#ffffff",
                                   accent_hover=accent_hover, **c))
