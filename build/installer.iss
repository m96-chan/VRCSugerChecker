; VRChat Sugar Checker - Inno Setup インストーラースクリプト
; https://jrsoftware.org/isinfo.php

#define MyAppName "VRChat Sugar Checker"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Your Name"
#define MyAppURL "https://github.com/yourusername/VRCSugerChecker"
#define MyAppExeName "VRChatSugarChecker.exe"

[Setup]
; アプリケーション情報
AppId={{8D3F5A2B-9C7E-4F1A-B6D8-1E9A4C5B7D2F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\README.md
InfoBeforeFile=..\README.md
OutputDir=..\dist
OutputBaseFilename=VRChatSugarChecker_Setup_{#MyAppVersion}
SetupIconFile=
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; アンインストール時の設定
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにアイコンを作成する"; GroupDescription: "追加のアイコン:"
Name: "startupicon"; Description: "スタートメニューにアイコンを作成する"; GroupDescription: "追加のアイコン:"; Flags: unchecked
Name: "autostart"; Description: "Windows起動時に自動実行する（バックグラウンドで動作）"; GroupDescription: "スタートアップ設定:"; Flags: unchecked

[Files]
; メインの実行ファイル
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; 設定ファイル
Source: "..\dist\config.example.json"; DestDir: "{app}"; Flags: ignoreversion
; スクリプトファイル
Source: "..\dist\run_silent.vbs"; DestDir: "{app}"; Flags: ignoreversion
; ドキュメント
Source: "..\dist\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "..\dist\DEVELOPMENT.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\BUILD_GUIDE.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\AUDIO_RECORDING.md"; DestDir: "{app}"; Flags: ignoreversion
; ログディレクトリ（空）
Source: "..\dist\logs\.gitkeep"; DestDir: "{app}\logs"; Flags: ignoreversion

[Dirs]
Name: "{app}\logs"; Permissions: users-full
Name: "{app}\logs\audio"; Permissions: users-full
Name: "{app}\logs\screenshots"; Permissions: users-full
Name: "{app}\logs\upload_temp"; Permissions: users-full

[Icons]
; スタートメニュー
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} (バックグラウンド実行)"; Filename: "{app}\run_silent.vbs"
Name: "{group}\設定ファイルを編集"; Filename: "notepad.exe"; Parameters: """{app}\config.json"""
Name: "{group}\README"; Filename: "{app}\README.md"
Name: "{group}\アンインストール"; Filename: "{uninstallexe}"

; デスクトップアイコン
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{autodesktop}\{#MyAppName} (バックグラウンド)"; Filename: "{app}\run_silent.vbs"; Tasks: desktopicon

; スタートメニュー（オプション）
Name: "{userstartmenu}\{#MyAppName}"; Filename: "{app}\run_silent.vbs"; Tasks: startupicon

[Registry]
; スタートアップ登録（autostart タスクが選択された場合）
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "VRChatSugarChecker"; ValueData: """{app}\run_silent.vbs"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; インストール後に設定ファイルを作成するか確認
Filename: "{app}\{#MyAppExeName}"; Description: "設定ファイル (config.json) を作成する"; Flags: postinstall shellexec skipifsilent nowait unchecked

[Code]
// インストール時に config.json が存在しない場合は config.example.json からコピー
procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigFile: String;
  ExampleFile: String;
begin
  if CurStep = ssPostInstall then
  begin
    ConfigFile := ExpandConstant('{app}\config.json');
    ExampleFile := ExpandConstant('{app}\config.example.json');

    // config.json が存在しない場合のみコピー
    if not FileExists(ConfigFile) then
    begin
      FileCopy(ExampleFile, ConfigFile, False);
      MsgBox('設定ファイル (config.json) を作成しました。' + #13#10 +
             'Discord WebHook URLなどを設定してください。' + #13#10 + #13#10 +
             'ファイルの場所: ' + ConfigFile,
             mbInformation, MB_OK);
    end;
  end;
end;

// アンインストール時の確認
function InitializeUninstall(): Boolean;
var
  Response: Integer;
begin
  Response := MsgBox('VRChat Sugar Checker をアンインストールしますか？' + #13#10 +
                     '設定ファイル (config.json) とログファイルも削除されます。',
                     mbConfirmation, MB_YESNO);
  Result := (Response = IDYES);
end;

// アンインストール時にログフォルダも削除
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  LogsDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    LogsDir := ExpandConstant('{app}\logs');
    if DirExists(LogsDir) then
    begin
      DelTree(LogsDir, True, True, True);
    end;
  end;
end;
