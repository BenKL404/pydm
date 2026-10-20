#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
# Installe PyDM pour l'utilisateur courant et le relie aux navigateurs
# (Firefox, Chrome, Chromium, Brave, Edge, Vivaldi, Opera).
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/pydm"
HOST_NAME="com.pydm.host"
CHROME_ID="feloklndigmnjlmffbddgcdfigpnbcba"
FIREFOX_ID="pydm@local"

if ! python3 -c "import venv, ensurepip" 2>/dev/null; then
    echo "✗ Module venv de Python manquant : sudo apt install python3-venv"
    exit 1
fi

mkdir -p "$DEST" "$HOME/.local/bin" "$HOME/.local/share/applications"
if [ ! -x "$DEST/venv/bin/python" ]; then
    echo "Création de l'environnement Python dans $DEST/venv…"
    python3 -m venv "$DEST/venv"
fi
if [ -z "$PYDM_SKIP_PIP" ]; then
    echo "Installation / mise à jour de PySide6 et yt-dlp (peut prendre quelques minutes)…"
    if ! "$DEST/venv/bin/python" -m pip install -q -U PySide6 yt-dlp; then
        if "$DEST/venv/bin/python" -c "import PySide6" 2>/dev/null; then
            echo "⚠ Mise à jour impossible (hors ligne ?) : PySide6 est déjà installé, on continue."
        else
            echo "✗ Échec de pip : vérifiez la connexion Internet puis relancez ./install.sh"
            exit 1
        fi
    fi
fi

rm -rf "$DEST/pydm" "$DEST/pydm.py"
cp -r "$SRC/pydm" "$DEST/pydm"
find "$DEST/pydm" -name __pycache__ -prune -exec rm -rf {} +
cp "$SRC/pydm_host.py" "$DEST/"
chmod +x "$DEST/pydm_host.py"
rm -f "$HOME/.local/bin/pydm"
# lanceur et entrée de menu écrits par Python : chemins correctement protégés (« " », « $ »…)
python3 - "$DEST" "$HOME/.local/bin/pydm" "$SRC/pydm.desktop" "$HOME/.local/share/applications/pydm.desktop" <<'PY'
import re, shlex, sys
dest, launcher, desktop_src, desktop_out = sys.argv[1:]
with open(launcher, "w") as f:
    f.write(f'#!/bin/sh\nPYTHONPATH={shlex.quote(dest)} exec {shlex.quote(dest + "/venv/bin/python")} -m pydm "$@"\n')
exec_path = re.sub(r'(["`$\\])', r"\\\1", launcher).replace("\\", "\\\\")   # règles des fichiers .desktop
with open(desktop_src) as f:
    text = re.sub(r"^Exec=.*$", lambda m: f'Exec="{exec_path}"', f.read(), flags=re.M)
with open(desktop_out, "w") as f:
    f.write(text)
PY
chmod +x "$HOME/.local/bin/pydm"

ICONS="$HOME/.local/share/icons/hicolor"
for size in 16 32 48 64 128 256 512; do
    png="$SRC/pydm/gui/icons/png/pydm-$size.png"
    if [ -f "$png" ]; then
        mkdir -p "$ICONS/${size}x$size/apps"
        cp "$png" "$ICONS/${size}x$size/apps/pydm.png"
    fi
done
if [ -f "$SRC/pydm/gui/icons/logo.svg" ]; then
    mkdir -p "$ICONS/scalable/apps"
    cp "$SRC/pydm/gui/icons/logo.svg" "$ICONS/scalable/apps/pydm.svg"
fi
echo "PyDM installé dans $DEST (commande : pydm)"

write_manifest() {   # $1 = dossier, $2 = clé (allowed_origins / allowed_extensions), $3 = valeur
    mkdir -p "$1"
    python3 -c 'import json, sys
folder, host, key, value, path = sys.argv[1:]
with open(f"{folder}/{host}.json", "w") as f:
    json.dump({"name": host, "description": "PyDM - gestionnaire de téléchargement", "path": path,
               "type": "stdio", key: [value]}, f, indent=2)' "$1" "$HOST_NAME" "$2" "$3" "$DEST/pydm_host.py"
    echo "  ✓ $1"
}

echo "Liaison avec les navigateurs :"
write_manifest "$HOME/.mozilla/native-messaging-hosts" allowed_extensions "$FIREFOX_ID"
for dir in google-chrome google-chrome-beta chromium BraveSoftware/Brave-Browser microsoft-edge vivaldi opera; do
    if [ -d "$HOME/.config/$dir" ] || [ "$dir" = google-chrome ]; then
        write_manifest "$HOME/.config/$dir/NativeMessagingHosts" allowed_origins "chrome-extension://$CHROME_ID/"
    fi
done

command -v ffmpeg >/dev/null || echo "⚠ ffmpeg manquant (meilleure qualité / MP3) : sudo apt install ffmpeg"
echo
echo "Il reste à charger l'extension dans le navigateur (voir LISEZMOI.md), puis à le redémarrer."
