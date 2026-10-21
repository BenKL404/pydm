# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
# Construit PyDM pour Windows : dist\PyDM-<version>-windows-portable.zip et, si Inno Setup est
# installé, dist\PyDM-<version>-Setup.exe. Variable PYDM_BUILD_CACHE : dossier des téléchargements.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Cache = if ($env:PYDM_BUILD_CACHE) { $env:PYDM_BUILD_CACHE } else { Join-Path $Root "packaging\cache" }
$Build = Join-Path $Root "build"
$Dist = Join-Path $Root "dist"
$Version = (Select-String -Path (Join-Path $Root "pydm\__init__.py") -Pattern '__version__ = "(.*)"').Matches[0].Groups[1].Value

# ffmpeg 9.0.2 « essentials » (gyan.dev), version figée et vérifiée
$FfmpegZip = "ffmpeg-9.0.2-essentials_build.zip"
$FfmpegUrl = "https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/$FfmpegZip"
$FfmpegSha256 = "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba"

New-Item -ItemType Directory -Force -Path $Cache, $Build, $Dist | Out-Null
$zip = Join-Path $Cache $FfmpegZip
if (-not (Test-Path $zip)) {
    Write-Host "Téléchargement de $FfmpegZip…"
    Invoke-WebRequest -Uri $FfmpegUrl -OutFile "$zip.part"
    Move-Item "$zip.part" $zip
}
if ((Get-FileHash $zip -Algorithm SHA256).Hash.ToLower() -ne $FfmpegSha256) { throw "Empreinte de $FfmpegZip incorrecte" }
$ff = Join-Path $Build "ffmpeg"
Remove-Item -Recurse -Force $ff -ErrorAction SilentlyContinue
Expand-Archive $zip -DestinationPath (Join-Path $Build "ffmpeg-zip") -Force
New-Item -ItemType Directory -Force -Path $ff | Out-Null
Get-ChildItem -Recurse (Join-Path $Build "ffmpeg-zip") -Include ffmpeg.exe, ffprobe.exe | Copy-Item -Destination $ff

$py = Join-Path $Build "venv\Scripts\python.exe"
if (-not (Test-Path $py)) { python -m venv (Join-Path $Build "venv") }
& $py -m pip install -q -U "pyinstaller==6.*" "PySide6==6.12.0" yt-dlp pillow
if ($LASTEXITCODE) { throw "pip a échoué" }

Write-Host "PyInstaller…"
$env:PYDM_FFMPEG_DIR = $ff
& $py -m PyInstaller --noconfirm --clean --distpath (Join-Path $Build "dist") --workpath (Join-Path $Build "work") (Join-Path $Root "packaging\pydm.spec")
if ($LASTEXITCODE) { throw "PyInstaller a échoué" }

$ico = Join-Path $Build "pydm.ico"
& $py -c "import sys; from PIL import Image; Image.open(sys.argv[1]).save(sys.argv[2], sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])" (Join-Path $Root "pydm\gui\icons\png\pydm-256.png") $ico
if ($LASTEXITCODE) { throw "icône .ico impossible" }

$app = Join-Path $Build "dist\pydm"
$portable = Join-Path $Dist "PyDM-$Version-windows-portable.zip"
Remove-Item -Force $portable -ErrorAction SilentlyContinue
Compress-Archive -Path $app -DestinationPath $portable
Write-Host "✓ $portable"

$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = (Get-Item "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" -ErrorAction SilentlyContinue).FullName }
if ($iscc) {
    & $iscc "/DAppVersion=$Version" "/DAppSource=$app" "/DAppIcon=$ico" "/O$Dist" (Join-Path $Root "packaging\windows\pydm.iss")
    if ($LASTEXITCODE) { throw "Inno Setup a échoué" }
    Write-Host "✓ $(Join-Path $Dist "PyDM-$Version-Setup.exe")"
} else {
    Write-Host "Inno Setup absent : installateur non construit"
}
