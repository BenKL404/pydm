# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
# Imite Firefox : ce processus se place dans un « job » Windows qui tue tous ses processus à sa
# fermeture (sortie autorisée, comme Firefox), lance l'hôte natif, écrit sa réponse, puis se termine.
# PyDM lancé par l'hôte doit survivre (CREATE_BREAKAWAY_FROM_JOB).
param([Parameter(Mandatory = $true)][string]$Host_, [Parameter(Mandatory = $true)][string]$Message,
      [Parameter(Mandatory = $true)][string]$Out)
$ErrorActionPreference = "Stop"
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Job {
    [StructLayout(LayoutKind.Sequential)] struct Basic {
        public long PerProcessUserTimeLimit, PerJobUserTimeLimit; public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize; public uint ActiveProcessLimit;
        public UIntPtr Affinity; public uint PriorityClass, SchedulingClass; }
    [StructLayout(LayoutKind.Sequential)] struct Io { public ulong a, b, c, d, e, f; }
    [StructLayout(LayoutKind.Sequential)] struct Extended {
        public Basic BasicLimitInformation; public Io IoInfo;
        public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed; }
    [DllImport("kernel32.dll", SetLastError = true)] static extern IntPtr CreateJobObject(IntPtr a, string n);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool SetInformationJobObject(IntPtr j, int c, ref Extended i, int l);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool AssignProcessToJobObject(IntPtr j, IntPtr p);
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
    public static void Enter() {
        IntPtr job = CreateJobObject(IntPtr.Zero, null);
        Extended info = new Extended();
        info.BasicLimitInformation.LimitFlags = 0x2000 | 0x800;   // KILL_ON_JOB_CLOSE | BREAKAWAY_OK
        if (!SetInformationJobObject(job, 9, ref info, Marshal.SizeOf(typeof(Extended))))
            throw new Exception("SetInformationJobObject " + Marshal.GetLastWin32Error());
        if (!AssignProcessToJobObject(job, GetCurrentProcess()))
            throw new Exception("AssignProcessToJobObject " + Marshal.GetLastWin32Error());
    }
}
"@
[Job]::Enter()
$body = [Text.Encoding]::UTF8.GetBytes($Message)
$psi = New-Object Diagnostics.ProcessStartInfo $Host_
$psi.Arguments = "chrome-extension://feloklndigmnjlmffbddgcdfigpnbcba/ --parent-window=0"
$psi.UseShellExecute = $false
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$p = [Diagnostics.Process]::Start($psi)
$p.StandardInput.BaseStream.Write([BitConverter]::GetBytes([int]$body.Length), 0, 4)
$p.StandardInput.BaseStream.Write($body, 0, $body.Length)
$p.StandardInput.Close()
$buf = New-Object IO.MemoryStream
$p.StandardOutput.BaseStream.CopyTo($buf)
$p.WaitForExit(60000) | Out-Null
$bytes = $buf.ToArray()
$reply = if ($bytes.Length -ge 4) { [Text.Encoding]::UTF8.GetString($bytes, 4, $bytes.Length - 4) } else { "" }
Set-Content -Path $Out -Value $reply -Encoding utf8
# fin du processus : le job se ferme et Windows tue tout ce qui y est resté
