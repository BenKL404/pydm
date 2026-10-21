; SPDX-License-Identifier: GPL-3.0-or-later
; Copyright (C) 2026 Kokou Bernard KPEDZI
; Installateur Windows de PyDM (Inno Setup 6), par utilisateur, sans droits administrateur.
; iscc /DAppVersion=1.4.0 /DAppSource=<dossier PyInstaller> /O<sortie> pydm.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppIcon
  #define AppIcon "..\..\build\pydm.ico"
#endif
#ifndef AppSource
  #define AppSource "..\..\build\dist\pydm"
#endif

[Setup]
AppId={{6F1D2C4E-5B8A-4C3E-9D7F-2A1B0C9E8D71}
AppName=PyDM
AppVersion={#AppVersion}
AppVerName=PyDM {#AppVersion}
AppPublisher=Kokou Bernard KPEDZI
AppPublisherURL=https://github.com/BenKL404/pydm
AppSupportURL=https://github.com/BenKL404/pydm/issues
DefaultDirName={localappdata}\Programs\PyDM
DefaultGroupName=PyDM
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
OutputBaseFilename=PyDM-{#AppVersion}-Setup
SetupIconFile={#AppIcon}
UninstallDisplayIcon={app}\pydm.exe
LicenseFile=..\..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PyDM"; Filename: "{app}\pydm.exe"
Name: "{autodesktop}\PyDM"; Filename: "{app}\pydm.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\pydm.exe"; Description: "{cm:LaunchProgram,PyDM}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; retire les clés du registre et les manifestes des navigateurs avant de supprimer les fichiers
Filename: "{app}\pydm.exe"; Parameters: "--remove-integration"; RunOnceId: "RemoveIntegration"; Flags: runhidden waituntilterminated
