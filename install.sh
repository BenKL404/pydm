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

mkdir -p "$DEST" "$HOME/.local/bin" "$HOME/.local/share/applications"
cp "$SRC/pydm.py" "$SRC/pydm_host.py" "$DEST/"
chmod +x "$DEST/pydm.py" "$DEST/pydm_host.py"
ln -sf "$DEST/pydm.py" "$HOME/.local/bin/pydm"
sed "s|^Exec=.*|Exec=python3 $DEST/pydm.py|" "$SRC/pydm.desktop" > "$HOME/.local/share/applications/pydm.desktop"
echo "PyDM installé dans $DEST (commande : pydm)"

write_manifest() {   # $1 = dossier, $2 = clé (allowed_origins / allowed_extensions), $3 = valeur
    mkdir -p "$1"
    cat > "$1/$HOST_NAME.json" <<EOF
{
  "name": "$HOST_NAME",
  "description": "PyDM - gestionnaire de téléchargement",
  "path": "$DEST/pydm_host.py",
  "type": "stdio",
  "$2": ["$3"]
}
EOF
    echo "  ✓ $1"
}

echo "Liaison avec les navigateurs :"
write_manifest "$HOME/.mozilla/native-messaging-hosts" allowed_extensions "$FIREFOX_ID"
for dir in google-chrome google-chrome-beta chromium BraveSoftware/Brave-Browser microsoft-edge vivaldi opera; do
    if [ -d "$HOME/.config/$dir" ] || [ "$dir" = google-chrome ]; then
        write_manifest "$HOME/.config/$dir/NativeMessagingHosts" allowed_origins "chrome-extension://$CHROME_ID/"
    fi
done

python3 -c "import tkinter" 2>/dev/null || echo "⚠ Tkinter manquant : sudo apt install python3-tk"
python3 -c "import yt_dlp" 2>/dev/null || echo "⚠ yt-dlp manquant (vidéos) : pip install -U yt-dlp"
command -v ffmpeg >/dev/null || echo "⚠ ffmpeg manquant (meilleure qualité / MP3) : sudo apt install ffmpeg"
echo
echo "Il reste à charger l'extension dans le navigateur (voir LISEZMOI.md), puis à le redémarrer."
