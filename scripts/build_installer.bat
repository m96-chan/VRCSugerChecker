@echo off
REM VRChat Sugar Checker - インストーラービルドスクリプト
REM 前提: Inno Setup がインストールされている必要があります
REM https://jrsoftware.org/isinfo.php

echo ========================================
echo VRChat Sugar Checker - インストーラー作成
echo ========================================
echo.

REM プロジェクトルートに移動
cd /d "%~dp0\.."

REM まず通常のビルドを実行
echo [1/2] PyInstallerでビルド中...
call scripts\build.bat
if errorlevel 1 (
    echo.
    echo [エラー] ビルドに失敗しました
    pause
    exit /b 1
)

echo.
echo [2/2] Inno Setupでインストーラーを作成中...

REM Inno Setupのパスを設定
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

REM Inno Setupがインストールされているか確認
if not exist %ISCC% (
    echo.
    echo [エラー] Inno Setupが見つかりません
    echo Inno Setupをインストールしてください: https://jrsoftware.org/isinfo.php
    echo.
    pause
    exit /b 1
)

REM インストーラーをビルド
%ISCC% "installer\installer.iss"
if errorlevel 1 (
    echo.
    echo [エラー] インストーラーの作成に失敗しました
    pause
    exit /b 1
)

echo.
echo ========================================
echo インストーラーの作成が完了しました！
echo ========================================
echo.
echo インストーラー: dist\VRChatSugarChecker_Setup_*.exe
echo.
dir /b dist\VRChatSugarChecker_Setup_*.exe
echo.
pause
