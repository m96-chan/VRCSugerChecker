#!/bin/bash
# VRChat Sugar Checker - ビルドスクリプト (Linux/WSL)
# このスクリプトを実行すると、実行ファイル (.exe) が生成されます

set -e

echo "========================================"
echo "VRChat Sugar Checker - ビルド開始"
echo "========================================"
echo ""

# 依存関係のインストール確認
echo "[1/4] 依存関係を確認中..."
python3 -m pip install -r requirements.txt
echo ""

# 古いビルドファイルを削除
echo "[2/4] 古いビルドファイルを削除中..."
rm -rf build dist
echo ""

# PyInstallerでビルド
echo "[3/4] PyInstallerでビルド中..."
echo "この処理には数分かかる場合があります..."
python3 -m PyInstaller VRChatSugarChecker.spec
echo ""

# 必要なファイルをdistフォルダにコピー
echo "[4/4] 必要なファイルをコピー中..."
mkdir -p dist/logs
cp logs/.gitkeep dist/logs/ 2>/dev/null || true
cp config.example.json dist/ 2>/dev/null || true
cp run_silent.vbs dist/ 2>/dev/null || true
cp install_startup.ps1 dist/ 2>/dev/null || true
cp uninstall_startup.ps1 dist/ 2>/dev/null || true
cp README.md dist/ 2>/dev/null || true
echo ""

echo "========================================"
echo "ビルド完了！"
echo "========================================"
echo ""
echo "実行ファイル: dist/VRChatSugarChecker.exe"
echo ""
echo "配布方法:"
echo "1. dist フォルダの内容をすべてコピー"
echo "2. ユーザーに配布"
echo ""
echo "注意:"
echo "- config.example.json を config.json にコピーして設定してください"
echo "- logsフォルダは自動的に作成されます"
echo ""
