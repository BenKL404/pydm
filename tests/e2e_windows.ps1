# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
# Essai de bout en bout de l'installateur Windows (CI) : installation silencieuse, intégration,
# hôte natif utilisé comme par le navigateur, vrai téléchargement, désinstallation.
param([Parameter(Mandatory = $true)][string]$Setup)
$ErrorActionPreference = "Stop"
$env:QT_QPA_PLATFORM = "offscreen"
$App = Join-Path $env:LOCALAPPDATA "Programs\PyDM"
$MozKey = "HKCU:\Software\Mozilla\NativeMessagingHosts\com.pydm.host"
$Keys = @($MozKey, "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.pydm.host",
          "HKCU:\Software\Chromium\NativeMessagingHosts\com.pydm.host",
          "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\com.pydm.host")

function Wait-Until([scriptblock]$Cond, [int]$Seconds, [string]$What) {
    $end = (Get-Date).AddSeconds($Seconds)
    while (-not (& $Cond)) {
        if ((Get-Date) -gt $end) { throw "Délai dépassé : $What" }
        Start-Sleep -Milliseconds 500
    }
}

function Send-Native([hashtable]$Msg) {
    # cadre de la messagerie native : longueur sur 4 octets (petit-boutiste) puis JSON
    $body = [Text.Encoding]::UTF8.GetBytes(($Msg | ConvertTo-Json -Compress))
    $psi = New-Object Diagnostics.ProcessStartInfo (Join-Path $App "pydm-host.exe")
    $psi.Arguments = "chrome-extension://feloklndigmnjlmffbddgcdfigpnbcba/ --parent-window=0"
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $p = [Diagnostics.Process]::Start($psi)
    $p.StandardInput.BaseStream.Write([BitConverter]::GetBytes([int]$body.Length), 0, 4)
    $p.StandardInput.BaseStream.Write($body, 0, $body.Length)
    $p.StandardInput.Close()
    $out = New-Object IO.MemoryStream
    $p.StandardOutput.BaseStream.CopyTo($out)
    if (-not $p.WaitForExit(60000)) { $p.Kill(); throw "pydm-host.exe ne se termine pas" }
    $bytes = $out.ToArray()
    if ($bytes.Length -lt 4) { throw "pydm-host.exe n'a rien répondu (code $($p.ExitCode))" }
    return [Text.Encoding]::UTF8.GetString($bytes, 4, $bytes.Length - 4) | ConvertFrom-Json
}

Write-Host "== Installation silencieuse"
$p = Start-Process $Setup -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-" -PassThru -Wait
if ($p.ExitCode) { throw "Installation : code $($p.ExitCode)" }
foreach ($f in "pydm.exe", "pydm-host.exe", "_internal\ffmpeg.exe") {
    if (-not (Test-Path (Join-Path $App $f))) { throw "Fichier absent : $f" }
}

Write-Host "== Premier lancement : intégration"
$gui = Start-Process (Join-Path $App "pydm.exe") -ArgumentList "--minimized" -PassThru
Wait-Until { Test-Path $MozKey } 60 "clé du registre Mozilla"
foreach ($k in $Keys) {
    $manifest = (Get-Item $k).GetValue("")
    $json = Get-Content $manifest -Raw | ConvertFrom-Json
    if ($json.path -ne (Join-Path $App "pydm-host.exe")) { throw "Manifeste $manifest : path = $($json.path)" }
}
Write-Host "   clés et manifestes OK"

Write-Host "== Hôte natif : ping, PyDM ouvert"
$r = Send-Native @{ action = "ping" }
if (-not $r.ok -or -not $r.ytdlp) { throw "ping : $($r | ConvertTo-Json -Compress)" }

Write-Host "== Hôte natif lancé comme par Firefox (job), PyDM fermé : relance, téléchargement, survie"
Stop-Process -Id $gui.Id -Force
Get-Process pydm -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
$srv = Join-Path $env:TEMP "pydm-e2e-srv"
$dl = Join-Path $env:TEMP "pydm-e2e-dl"
New-Item -ItemType Directory -Force -Path $srv, $dl | Out-Null
$data = New-Object byte[] (3MB)
(New-Object Random 42).NextBytes($data)
[IO.File]::WriteAllBytes((Join-Path $srv "essai.bin"), $data)
$http = Start-Process python -ArgumentList "-m", "http.server", "8765", "--bind", "127.0.0.1", "--directory", $srv -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 2
# réglages : pas de fenêtre de confirmation, dossier de téléchargement de l'essai
$cfg = Join-Path $env:APPDATA "PyDM"
New-Item -ItemType Directory -Force -Path $cfg | Out-Null
@{ confirm_add = $false; show_progress = $false; folder = $dl; sort_by_type = $false } | ConvertTo-Json | Set-Content (Join-Path $cfg "settings.json") -Encoding utf8
$reply = Join-Path $env:TEMP "pydm-e2e-reply.json"
$msgFile = Join-Path $env:TEMP "pydm-e2e-msg.json"
$msg = @{ action = "add"; url = "http://127.0.0.1:8765/essai.bin"; kind = "file" } | ConvertTo-Json -Compress
[IO.File]::WriteAllText($msgFile, $msg, (New-Object Text.UTF8Encoding $false))
$j = Start-Process pwsh -ArgumentList "-NoProfile", "-File", (Join-Path $PSScriptRoot "e2e_windows_job.ps1"),
    "-Host_", (Join-Path $App "pydm-host.exe"), "-MessageFile", $msgFile, "-Out", $reply -PassThru -Wait -NoNewWindow
if ($j.ExitCode) { throw "Lanceur en job : code $($j.ExitCode)" }
$r = Get-Content $reply -Raw | ConvertFrom-Json
if (-not $r.ok) { throw "add : $(Get-Content $reply -Raw)" }
Start-Sleep -Seconds 3
if (-not (Get-Process pydm -ErrorAction SilentlyContinue)) { throw "PyDM tué avec le job du navigateur" }
Write-Host "   PyDM a survécu au job du navigateur"
$target = Join-Path $dl "essai.bin"
Wait-Until { (Test-Path $target) -and -not (Test-Path "$target.part") -and ((Get-Item $target).Length -eq 3MB) } 90 "téléchargement de essai.bin"
Write-Host "   téléchargement OK (3 Mo)"
Stop-Process -Id $http.Id -Force

Write-Host "== Désinstallation refusée tant que PyDM tourne"
if (-not (Get-Process pydm -ErrorAction SilentlyContinue)) { throw "PyDM devrait encore tourner" }
Start-Process (Join-Path $App "unins000.exe") -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait | Out-Null
Start-Sleep -Seconds 10
if (-not (Test-Path (Join-Path $App "pydm.exe")) -or -not (Test-Path $MozKey)) { throw "Désinstallé alors que PyDM tournait" }
Write-Host "   refusée, rien de supprimé"

Write-Host "== Désinstallation silencieuse"
Get-Process pydm -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
$p = Start-Process (Join-Path $App "unins000.exe") -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -PassThru -Wait
if ($p.ExitCode) { throw "Désinstallation : code $($p.ExitCode)" }
Wait-Until { -not (Test-Path (Join-Path $App "pydm.exe")) } 60 "suppression des fichiers"
foreach ($k in $Keys) { if (Test-Path $k) { throw "Clé restée après désinstallation : $k" } }
Write-Host "✓ Essai de bout en bout réussi"
