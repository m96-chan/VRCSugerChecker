; VRChat Sugar Checker - Inno Setup Installer Script
; https://jrsoftware.org/isinfo.php

#define MyAppName "VRChat Sugar Checker"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "m96-chan"
#define MyAppURL "https://github.com/m96-chan/VRCSugerChecker"
#define MyAppExeName "VRChatSugarChecker.exe"

[Setup]
; Basic app information
AppId={{A7B8C9D0-E1F2-4A5B-9C8D-7E6F5A4B3C2D}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Installation directory
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Privileges
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Output configuration
OutputDir=..\dist
OutputBaseFilename=VRChatSugarChecker_Setup_{#MyAppVersion}
SetupIconFile=
Compression=lzma
SolidCompression=yes

; Modern UI
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Windows起動時に自動実行（バックグラウンド）"; GroupDescription: "追加オプション:"; Flags: unchecked

[Files]
; Main executable
Source: "..\dist\VRChatSugarChecker.exe"; DestDir: "{app}"; Flags: ignoreversion

; Configuration files
Source: "..\config.example.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config.example.json"; DestDir: "{app}"; DestName: "config.json"; Flags: onlyifdoesntexist

; Scripts
Source: "..\scripts\run_silent.vbs"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\scripts\install_startup.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\scripts\uninstall_startup.ps1"; DestDir: "{app}"; Flags: ignoreversion

; Documentation
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\DEVELOPMENT.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "..\docs\BUILD_GUIDE.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\AUDIO_RECORDING.md"; DestDir: "{app}\docs"; Flags: ignoreversion

; Logs directory placeholder
Source: "..\logs\.gitkeep"; DestDir: "{app}\logs"; Flags: ignoreversion
Source: "..\logs\.gitkeep"; DestDir: "{app}\logs\audio"; Flags: ignoreversion
Source: "..\logs\.gitkeep"; DestDir: "{app}\logs\screenshots"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Option to run the application after installation
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

; Install to startup if selected
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\install_startup.ps1"""; Flags: runhidden; Tasks: autostart

[UninstallRun]
; Remove from startup on uninstall
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\uninstall_startup.ps1"""; Flags: runhidden

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Create logs directories if they don't exist
    if not DirExists(ExpandConstant('{app}\logs')) then
      CreateDir(ExpandConstant('{app}\logs'));
    if not DirExists(ExpandConstant('{app}\logs\audio')) then
      CreateDir(ExpandConstant('{app}\logs\audio'));
    if not DirExists(ExpandConstant('{app}\logs\screenshots')) then
      CreateDir(ExpandConstant('{app}\logs\screenshots'));
  end;
end;
