@echo off
REM VRChat Sugar Checker - ビルドスクリプト (Windows)
REM このスクリプトを実行すると、実行ファイル (.exe) が生成されます

REM プロジェクトルートに移動
cd /d "%~dp0\.."

echo ========================================
echo VRChat Sugar Checker - ビルド開始
echo ========================================
echo.

REM 依存関係のインストール確認
echo [1/4] 依存関係を確認中...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo エラー: 依存関係のインストールに失敗しました
    pause
    exit /b 1
)
echo.

REM 古いビルドファイルを削除
echo [2/4] 古いビルドファイルを削除中...
if exist "build\build" rmdir /s /q "build\build"
if exist "build\dist" rmdir /s /q "build\dist"
if exist "dist" rmdir /s /q "dist"
echo.

REM PyInstallerでビルド
echo [3/4] PyInstallerでビルド中...
echo この処理には数分かかる場合があります...
cd installer
python -m PyInstaller --distpath ../dist --workpath ../build/build VRChatSugarChecker.spec
if errorlevel 1 (
    echo エラー: ビルドに失敗しました
    pause
    exit /b 1
)
cd ..
echo.

REM 必要なファイルをdistフォルダにコピー
echo [4/4] 必要なファイルをコピー中...
if not exist "dist\logs" mkdir "dist\logs"
copy "logs\.gitkeep" "dist\logs\" >nul 2>&1
copy "config.example.json" "dist\" >nul 2>&1
copy "scripts\run_silent.vbs" "dist\" >nul 2>&1
copy "scripts\install_startup.ps1" "dist\" >nul 2>&1
copy "scripts\uninstall_startup.ps1" "dist\" >nul 2>&1
copy "README.md" "dist\" >nul 2>&1
echo.

echo ========================================
echo ビルド完了！
echo ========================================
echo.
echo 実行ファイル: dist\VRChatSugarChecker.exe
echo.
echo 配布方法:
echo 1. dist フォルダの内容をすべてコピー
echo 2. ユーザーに配布
echo.
echo 注意:
echo - config.example.json を config.json にコピーして設定してください
echo - logsフォルダは自動的に作成されます
echo.
pause
