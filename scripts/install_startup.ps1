# VRChat Sugar Checker - スタートアップ登録スクリプト
# このスクリプトをPowerShellで実行すると、Windowsスタートアップに登録されます

# 管理者権限チェック
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "[警告] このスクリプトは管理者権限なしで実行されています" -ForegroundColor Yellow
    Write-Host "通常ユーザーのスタートアップフォルダに登録します" -ForegroundColor Yellow
}

# スクリプトのディレクトリを取得
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# VBSファイルのパス
$vbsPath = Join-Path $scriptDir "run_silent.vbs"

# VBSファイルの存在確認
if (-not (Test-Path $vbsPath)) {
    Write-Host "[エラー] run_silent.vbs が見つかりません: $vbsPath" -ForegroundColor Red
    Write-Host "スクリプトが正しいディレクトリで実行されているか確認してください" -ForegroundColor Red
    exit 1
}

# スタートアップフォルダのパスを取得
$startupFolder = [Environment]::GetFolderPath("Startup")
Write-Host "[INFO] スタートアップフォルダ: $startupFolder" -ForegroundColor Cyan

# ショートカットのパス
$shortcutPath = Join-Path $startupFolder "VRChatSugarChecker.lnk"

# ショートカットを作成
$WScriptShell = New-Object -ComObject WScript.Shell
$shortcut = $WScriptShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $vbsPath
$shortcut.WorkingDirectory = $scriptDir
$shortcut.Description = "VRChat Sugar Checker - VRChatプロセス監視ツール"
$shortcut.Save()

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "スタートアップ登録が完了しました！" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "登録内容:" -ForegroundColor Cyan
Write-Host "  - ショートカット: $shortcutPath" -ForegroundColor White
Write-Host "  - VBSスクリプト: $vbsPath" -ForegroundColor White
Write-Host "  - 作業ディレクトリ: $scriptDir" -ForegroundColor White
Write-Host ""
Write-Host "次回のWindowsログイン時から自動的に起動します" -ForegroundColor Yellow
Write-Host "今すぐ起動する場合は、run_silent.vbs をダブルクリックしてください" -ForegroundColor Yellow
Write-Host ""
Write-Host "アンインストール方法:" -ForegroundColor Cyan
Write-Host "  以下のファイルを削除してください:" -ForegroundColor White
Write-Host "  $shortcutPath" -ForegroundColor White
Write-Host ""
