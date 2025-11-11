# VRChat Sugar Checker - スタートアップ削除スクリプト
# このスクリプトをPowerShellで実行すると、スタートアップから削除されます

# スタートアップフォルダのパスを取得
$startupFolder = [Environment]::GetFolderPath("Startup")
Write-Host "[INFO] スタートアップフォルダ: $startupFolder" -ForegroundColor Cyan

# ショートカットのパス
$shortcutPath = Join-Path $startupFolder "VRChatSugarChecker.lnk"

# ショートカットの存在確認
if (Test-Path $shortcutPath) {
    # ショートカットを削除
    Remove-Item $shortcutPath -Force
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Green
    Write-Host "スタートアップから削除しました" -ForegroundColor Green
    Write-Host "================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "削除したファイル: $shortcutPath" -ForegroundColor White
    Write-Host ""
    Write-Host "次回のWindowsログイン時から自動起動されなくなります" -ForegroundColor Yellow
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "[INFO] スタートアップにVRChat Sugar Checkerは登録されていません" -ForegroundColor Yellow
    Write-Host "ファイルが見つかりません: $shortcutPath" -ForegroundColor Yellow
    Write-Host ""
}
