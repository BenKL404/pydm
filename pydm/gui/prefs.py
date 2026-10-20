# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Fenêtre Préférences et démarrage avec la session."""
import os

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLineEdit, QSpinBox, QToolButton, QWidget)

from .. import store
from . import theme

THEMES = (("system", "Système"), ("light", "Clair"), ("dark", "Sombre"))
CATEGORY_LABELS = (("video", "Vidéos"), ("music", "Musique"), ("document", "Documents"), ("image", "Images"),
                   ("archive", "Archives"), ("program", "Programmes"))
AUTOSTART = """[Desktop Entry]
Type=Application
Name=PyDM
Comment=Gestionnaire de téléchargement multi-connexions
Exec="{launcher}" --minimized
Icon=pydm
Terminal=false
X-GNOME-Autostart-enabled=true
"""


def set_autostart(enabled, home=None):
    home = home or os.path.expanduser("~")
    path = os.path.join(home, ".config", "autostart", "pydm.desktop")
    if enabled:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(AUTOSTART.format(launcher=os.path.join(home, ".local", "bin", "pydm")))
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


class PreferencesDialog(QDialog):
    def __init__(self, settings, tray_available, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Préférences")
        self.setWindowIcon(theme.logo())
        form = QFormLayout(self)

        self.folder_edit = QLineEdit(settings["folder"])
        browse = QToolButton()
        browse.setIcon(theme.icon("folder"))
        browse.setToolTip("Choisir le dossier")
        browse.clicked.connect(self._browse)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.folder_edit, 1)
        h.addWidget(browse)
        form.addRow("Dossier de téléchargement", row)

        self.sort_box = QCheckBox("Ranger par type de fichier (sous-dossiers du dossier de téléchargement)")
        self.sort_box.setChecked(settings["sort_by_type"])
        form.addRow("", self.sort_box)
        self.dir_edits = {}
        dirs = settings.get("category_dirs") or {}
        for key, label in CATEGORY_LABELS:
            edit = QLineEdit(dirs.get(key) or store.DEFAULTS["category_dirs"][key])
            edit.setToolTip("Nom d'un sous-dossier, ou chemin complet (ex. /media/disque/Films)")
            edit.setEnabled(self.sort_box.isChecked())
            self.sort_box.toggled.connect(edit.setEnabled)
            self.dir_edits[key] = edit
            form.addRow(f"    {label}", edit)

        self.parts_spin = QSpinBox()
        self.parts_spin.setRange(1, 32)
        self.parts_spin.setValue(settings["parts"])
        form.addRow("Connexions par téléchargement", self.parts_spin)

        self.theme_box = QComboBox()
        self.theme_box.addItems([label for _, label in THEMES])
        self.theme_box.setCurrentText(dict(THEMES)[settings["theme"]])
        form.addRow("Thème", self.theme_box)

        self.clipboard_box = QCheckBox("Surveiller le presse-papiers")
        self.clipboard_box.setChecked(settings["clipboard"])
        self.notify_box = QCheckBox("Notifications de fin et d'erreur")
        self.notify_box.setChecked(settings["notify"])
        self.close_to_tray_box = QCheckBox("Fermer la fenêtre garde PyDM dans la barre système")
        self.close_to_tray_box.setChecked(settings["close_to_tray"] and tray_available)
        self.close_to_tray_box.setEnabled(tray_available)
        if not tray_available:
            self.close_to_tray_box.setToolTip("Barre système indisponible sur ce bureau")
        self.confirm_box = QCheckBox("Demander avant chaque téléchargement (qualité, nom, dossier)")
        self.confirm_box.setChecked(settings["confirm_add"])
        self.autostart_box = QCheckBox("Démarrer PyDM avec la session")
        self.autostart_box.setChecked(settings["autostart"])
        for box in (self.confirm_box, self.clipboard_box, self.notify_box, self.close_to_tray_box,
                    self.autostart_box):
            form.addRow("", box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Dossier de téléchargement", self.folder_edit.text())
        if path:
            self.folder_edit.setText(path)

    def result_settings(self):
        result = dict(self.settings)
        labels = {label: key for key, label in THEMES}
        result.update(
            folder=self.folder_edit.text().strip() or self.settings["folder"],
            parts=self.parts_spin.value(),
            theme=labels[self.theme_box.currentText()],
            clipboard=self.clipboard_box.isChecked(),
            notify=self.notify_box.isChecked(),
            close_to_tray=self.close_to_tray_box.isChecked() if self.close_to_tray_box.isEnabled()
            else self.settings["close_to_tray"],
            autostart=self.autostart_box.isChecked(),
            confirm_add=self.confirm_box.isChecked(),
            sort_by_type=self.sort_box.isChecked(),
            category_dirs={k: e.text().strip() or store.DEFAULTS["category_dirs"][k]
                           for k, e in self.dir_edits.items()},
        )
        return result
