#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
# Construit dist/PyDM-<version>-x86_64.AppImage : PyInstaller, puis AppDir, puis appimagetool.
# Variable PYDM_BUILD_CACHE : dossier des téléchargements (défaut : packaging/cache).
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="${PYDM_BUILD_CACHE:-$ROOT/packaging/cache}"
BUILD="$ROOT/build"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/pydm/__init__.py")"
OUT="$ROOT/dist/PyDM-$VERSION-x86_64.AppImage"

# sources figées et vérifiées
FFMPEG_URL="https://github.com/eugeneware/ffmpeg-static/releases/download/b6.1.1"   # ffmpeg 6.1.1 statique, GPL
FFMPEG_SHA256="bfe8a8fc511530457b528c48d77b5737527b504a3797a9bc4866aeca69c2dffa"
FFPROBE_SHA256="25d9b6ccb05e3d9de9e04e31e2506d8dd7f9f0418981965ac6df12e8d3afd067"
APPIMAGETOOL="appimagetool-1.9.1-x86_64.AppImage"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
APPIMAGETOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"

fetch() {   # $1 = fichier dans le cache, $2 = URL, $3 = SHA-256
    if [ ! -f "$CACHE/$1" ]; then
        echo "Téléchargement de $1…"
        curl -fsSL --retry 5 -C - -o "$CACHE/$1.part" "$2"
        mv "$CACHE/$1.part" "$CACHE/$1"
    fi
    echo "$3  $CACHE/$1" | sha256sum -c --quiet -
}

mkdir -p "$CACHE" "$BUILD" "$ROOT/dist"
fetch ffmpeg-6.1.1-linux-x64.gz "$FFMPEG_URL/ffmpeg-linux-x64.gz" "$FFMPEG_SHA256"
fetch ffprobe-6.1.1-linux-x64.gz "$FFMPEG_URL/ffprobe-linux-x64.gz" "$FFPROBE_SHA256"
fetch "$APPIMAGETOOL" "$APPIMAGETOOL_URL" "$APPIMAGETOOL_SHA256"
chmod +x "$CACHE/$APPIMAGETOOL"

rm -rf "$BUILD/ffmpeg"
mkdir -p "$BUILD/ffmpeg"
for tool in ffmpeg ffprobe; do
    gzip -dc "$CACHE/$tool-6.1.1-linux-x64.gz" > "$BUILD/ffmpeg/$tool"
    chmod +x "$BUILD/ffmpeg/$tool"
done

if [ ! -x "$BUILD/venv/bin/python" ]; then
    python3 -m venv "$BUILD/venv"
fi
"$BUILD/venv/bin/python" -m pip install -q -U "pyinstaller==6.*" "PySide6==6.12.0" yt-dlp

echo "PyInstaller…"
PYDM_FFMPEG_DIR="$BUILD/ffmpeg" "$BUILD/venv/bin/python" -m PyInstaller --noconfirm --clean \
    --distpath "$BUILD/dist" --workpath "$BUILD/work" "$ROOT/packaging/pydm.spec"

APPDIR="$BUILD/PyDM.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp -a "$BUILD/dist/pydm/." "$APPDIR/usr/bin/"
cp "$ROOT/packaging/AppRun" "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun"
cp "$ROOT/pydm.desktop" "$APPDIR/pydm.desktop"
cp "$ROOT/pydm/gui/icons/png/pydm-256.png" "$APPDIR/pydm.png"
ln -s pydm.png "$APPDIR/.DirIcon"

echo "appimagetool…"
rm -f "$OUT"
ARCH=x86_64 "$CACHE/$APPIMAGETOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$OUT"
echo "✓ $OUT ($(du -h "$OUT" | cut -f1))"
