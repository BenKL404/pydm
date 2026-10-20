# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Fenêtre Planification (file, limite, plage horaire) et action à la fin de la file."""
import subprocess

from PySide6.QtCore import QTime, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLabel, QPushButton, QSpinBox, QTimeEdit, QVBoxLayout, QWidget)

from ..scheduler import parse_hhmm
from . import theme

ACTIONS = (("none", "Ne rien faire"), ("quit", "Quitter PyDM"), ("suspend", "Mettre en veille"),
           ("poweroff", "Éteindre l'ordinateur"))
COUNTDOWN = {"quit": "Quitter PyDM", "suspend": "Mettre en veille", "poweroff": "Éteindre l'ordinateur"}


def _qtime(text):
    t = parse_hhmm(text)
    return QTime(t.hour, t.minute) if t else QTime(0, 0)


class ScheduleDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Planification")
        self.setWindowIcon(theme.logo())
        form = QFormLayout(self)
        self.max_spin = QSpinBox()
        self.max_spin.setRange(1, 10)
        self.max_spin.setValue(settings["max_active"])
        form.addRow("Téléchargements simultanés", self.max_spin)

        self.speed_box = QCheckBox("Limiter la vitesse totale à")
        self.speed_box.setChecked(settings["speed_on"])
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(16, 1_000_000)
        self.speed_spin.setSuffix(" Ko/s")
        self.speed_spin.setValue(settings["speed_kbps"])
        form.addRow(self.speed_box, self.speed_spin)

        self.window_box = QCheckBox("Plage horaire de la file planifiée")
        self.window_box.setChecked(settings["schedule_on"])
        self.start_edit, self.end_edit = QTimeEdit(), QTimeEdit()
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        for label, edit, key in (("de", self.start_edit, "schedule_start"), ("à", self.end_edit, "schedule_end")):
            edit.setDisplayFormat("HH:mm")
            edit.setTime(_qtime(settings[key]))
            h.addWidget(QLabel(label))
            h.addWidget(edit)
        h.addStretch(1)
        form.addRow(self.window_box, row)

        self.action_box = QComboBox()
        self.action_box.addItems([label for _, label in ACTIONS])
        self.action_box.setCurrentText(dict(ACTIONS)[settings["end_action"]])
        form.addRow("Quand la file est terminée", self.action_box)
        hint = QLabel("« Plus tard » ajoute à la file planifiée : elle démarre dans la plage horaire, "
                      "ou avec « Démarrer la file ».")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.colors()['muted']}; font-size: 11px;")
        form.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def result_settings(self):
        labels = {label: key for key, label in ACTIONS}
        return dict(self.settings, max_active=self.max_spin.value(), speed_on=self.speed_box.isChecked(),
                    speed_kbps=self.speed_spin.value(), schedule_on=self.window_box.isChecked(),
                    schedule_start=self.start_edit.time().toString("HH:mm"),
                    schedule_end=self.end_edit.time().toString("HH:mm"),
                    end_action=labels[self.action_box.currentText()])


class EndActionDialog(QDialog):
    """Compte à rebours avant l'action finale ; Annuler l'empêche."""
    confirmed = Signal()

    def __init__(self, action, seconds=60, parent=None):
        super().__init__(parent)
        self.action, self.remaining, self.done_ = action, seconds, False
        self.setWindowTitle("File terminée")
        self.setWindowIcon(theme.logo())
        lay = QVBoxLayout(self)
        self.label = QLabel()
        lay.addWidget(self.label)
        cancel = QPushButton("Annuler")
        cancel.clicked.connect(self.reject)
        lay.addWidget(cancel)
        self._render()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.step)
        self.timer.start(1000)

    def _render(self):
        self.label.setText(f"La file est terminée. {COUNTDOWN[self.action]} dans {self.remaining} s…")

    def step(self):
        if self.done_:
            return
        self.remaining -= 1
        if self.remaining <= 0:
            self.done_ = True
            self.timer.stop()
            self.accept()
            self.confirmed.emit()
            return
        self._render()

    def done(self, result):
        self.done_ = self.done_ or result == QDialog.Rejected
        self.timer.stop()
        super().done(result)


def run_end_action(action):
    """Mise en veille ou extinction ; renvoie un message d'erreur, ou None si tout va bien."""
    try:
        r = subprocess.run(["systemctl", action], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return f"systemctl {action} impossible : {e}"
    if r.returncode:
        return (r.stderr or "").strip() or f"systemctl {action} a échoué (code {r.returncode})"
    return None
