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

function Write-Framed([Diagnostics.Process]$P, [hashtable]$Msg) {
    $body = [Text.Encoding]::UTF8.GetBytes(($Msg | ConvertTo-Json -Compress))
    $P.StandardInput.BaseStream.Write([BitConverter]::GetBytes([int]$body.Length), 0, 4)
    $P.StandardInput.BaseStream.Write($body, 0, $body.Length)
    $P.StandardInput.BaseStream.Flush()
}

function Read-Exact([IO.Stream]$S, [int]$N, [int]$Seconds) {
    $buf = New-Object byte[] $N
    $got = 0
    while ($got -lt $N) {
        $task = $S.ReadAsync($buf, $got, $N - $got)
        if (-not $task.Wait([TimeSpan]::FromSeconds($Seconds))) { throw "Délai dépassé : lecture du pont" }
        if ($task.Result -le 0) { throw "Pont fermé par l'hôte natif" }
        $got += $task.Result
    }
    return , $buf       # virgule : sinon PowerShell déroule le tableau d'octets
}

function Read-Framed([Diagnostics.Process]$P, [int]$Seconds) {
    $stream = $P.StandardOutput.BaseStream
    $head = Read-Exact $stream 4 $Seconds
    $body = Read-Exact $stream ([BitConverter]::ToInt32($head, 0)) $Seconds
    return [Text.Encoding]::UTF8.GetString($body) | ConvertFrom-Json
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
# Process.Start et non Start-Process -Wait : ce dernier attend aussi les descendants, dont PyDM
$psi = New-Object Diagnostics.ProcessStartInfo "pwsh"
foreach ($a in "-NoProfile", "-File", (Join-Path $PSScriptRoot "e2e_windows_job.ps1"), "-Host_",
                (Join-Path $App "pydm-host.exe"), "-MessageFile", $msgFile, "-Out", $reply) { $psi.ArgumentList.Add($a) }
$psi.UseShellExecute = $false
$j = [Diagnostics.Process]::Start($psi)
if (-not $j.WaitForExit(120000)) { $j.Kill(); throw "Lanceur en job bloqué" }
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

Write-Host "== Pont permanent : PyDM redemande ses en-têtes au navigateur"
$urlFile = Join-Path $env:TEMP "pydm-e2e-url.txt"
Remove-Item $urlFile -ErrorAction SilentlyContinue
$guard = Start-Process python -ArgumentList (Join-Path $PSScriptRoot "e2e_cookie_server.py"), "3145728", "SID=2" `
    -PassThru -RedirectStandardOutput $urlFile
Wait-Until { (Test-Path $urlFile) -and ((Get-Content $urlFile -Raw) -match "^http://") } 30 "serveur protégé par cookie"
$base = (Get-Content $urlFile -Raw).Trim()
# l'hôte natif reste ouvert, comme le port runtime.connectNative de l'extension
$psi = New-Object Diagnostics.ProcessStartInfo (Join-Path $App "pydm-host.exe")
$psi.Arguments = "chrome-extension://feloklndigmnjlmffbddgcdfigpnbcba/ --parent-window=0"
$psi.UseShellExecute = $false
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$bridge = [Diagnostics.Process]::Start($psi)
Write-Framed $bridge @{ action = "bridge" }
Start-Sleep -Seconds 4      # le temps que l'hôte s'accroche à PyDM par le canal nommé
# cookie périmé : le serveur refuse, PyDM doit passer par le pont pour en obtenir un bon
$r = Send-Native @{ action = "add"; url = "$base/protege.bin"; kind = "file"; headers = @{ Cookie = "SID=1" } }
if (-not $r.ok) { throw "add (cookie périmé) : $($r | ConvertTo-Json -Compress)" }
$ask = Read-Framed $bridge 60
if ($ask.action -ne "refresh") { throw "demande inattendue sur le pont : $($ask | ConvertTo-Json -Compress)" }
if ($ask.url -ne "$base/protege.bin") { throw "lien inattendu sur le pont : $($ask.url)" }
if (-not $ask.id) { throw "demande sans identifiant" }
Write-Framed $bridge @{ id = $ask.id; headers = @{ Cookie = "SID=2" } }
$protege = Join-Path $dl "protege.bin"
Wait-Until { (Test-Path $protege) -and -not (Test-Path "$protege.part") -and ((Get-Item $protege).Length -eq 3MB) } `
    90 "téléchargement après rafraîchissement des en-têtes"
Write-Host "   en-têtes rafraîchis par le pont, téléchargement OK (3 Mo)"
$bridge.StandardInput.Close()
if (-not $bridge.WaitForExit(15000)) { $bridge.Kill(); throw "l'hôte du pont survit à la fermeture du port" }
Write-Host "   hôte du pont arrêté avec le port"
Stop-Process -Id $guard.Id -Force

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
