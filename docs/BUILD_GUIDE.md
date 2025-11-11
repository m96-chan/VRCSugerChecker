# VRChat Sugar Checker - ビルドガイド

PyInstallerを使用してPythonコードを実行ファイル (.exe) に変換する方法を説明します。

## 前提条件

- Python 3.7以上がインストールされていること
- Windows環境（WSLでも可能）

## ビルド手順

### 方法1: ビルドスクリプトを使用（推奨）

#### Windows の場合

```cmd
build.bat
```

#### Linux/WSL の場合

```bash
./build.sh
```

ビルドスクリプトは以下を自動的に実行します：
1. 依存関係のインストール
2. 古いビルドファイルの削除
3. PyInstallerでのビルド
4. 必要なファイルのコピー

### 方法2: 手動でビルド

#### 1. 依存関係をインストール

```bash
pip install -r requirements.txt
```

#### 2. PyInstallerでビルド

```bash
pyinstaller VRChatSugarChecker.spec
```

#### 3. 必要なファイルをコピー

```bash
# logsフォルダを作成
mkdir dist/logs
cp logs/.gitkeep dist/logs/

# 設定ファイルとスクリプトをコピー
cp config.example.json dist/
cp run_silent.vbs dist/
cp install_startup.ps1 dist/
cp uninstall_startup.ps1 dist/
cp README.md dist/
```

## ビルド結果

ビルドが完了すると、`dist` フォルダに以下のファイルが生成されます：

```
dist/
├── VRChatSugarChecker.exe     # 実行ファイル（メイン）
├── config.example.json         # 設定ファイルのサンプル
├── run_silent.vbs              # バックグラウンド起動用VBScript
├── install_startup.ps1         # スタートアップ登録スクリプト
├── uninstall_startup.ps1       # スタートアップ削除スクリプト
├── README.md                   # 使い方ドキュメント
└── logs/                       # ログフォルダ
    └── .gitkeep
```

## 配布方法

### 配布パッケージの作成

1. `dist` フォルダの内容をすべてZIPファイルにまとめる

```bash
# Windowsの場合
cd dist
powershell Compress-Archive -Path * -DestinationPath ../VRChatSugarChecker.zip

# Linux/WSLの場合
cd dist
zip -r ../VRChatSugarChecker.zip *
```

2. ZIPファイルをユーザーに配布

### ユーザーへの使用方法

配布されたZIPファイルを解凍後：

1. `config.example.json` を `config.json` にコピー
2. `config.json` を編集して設定を変更
3. `VRChatSugarChecker.exe` を実行

## ビルドのカスタマイズ

### コンソールを非表示にする

`VRChatSugarChecker.spec` の `console=True` を `console=False` に変更：

```python
exe = EXE(
    ...
    console=False,  # コンソールウィンドウを非表示
    ...
)
```

### アイコンを設定する

1. `icon.ico` ファイルを用意
2. `VRChatSugarChecker.spec` に追加：

```python
exe = EXE(
    ...
    icon='icon.ico',  # アイコンファイルのパス
    ...
)
```

### UPX圧縮を無効にする

ファイルサイズは大きくなりますが、一部のウイルス対策ソフトの誤検知を回避できます：

```python
exe = EXE(
    ...
    upx=False,  # UPX圧縮を無効化
    ...
)
```

## トラブルシューティング

### エラー: ModuleNotFoundError

**原因:** 必要なモジュールがインストールされていない

**解決方法:**
```bash
pip install -r requirements.txt
```

### エラー: UnicodeDecodeError

**原因:** ファイルのエンコーディング問題

**解決方法:**
- Python 3.8以上を使用
- または `VRChatSugarChecker.spec` の最初に `# -*- coding: utf-8 -*-` を追加

### 実行ファイルが大きすぎる

**原因:** 不要なモジュールが含まれている

**解決方法:**
1. `VRChatSugarChecker.spec` の `excludes` に不要なモジュールを追加：

```python
a = Analysis(
    ...
    excludes=['matplotlib', 'numpy', 'pandas'],  # 不要なモジュール
    ...
)
```

2. UPX圧縮を有効化（デフォルトで有効）

### ウイルス対策ソフトに検出される

**原因:** PyInstallerで生成された実行ファイルが誤検知されることがある

**解決方法:**
1. UPX圧縮を無効化
2. コード署名証明書で署名
3. ウイルス対策ソフトのホワイトリストに追加

## セキュリティに関する注意

### コードの保護レベル

PyInstallerでビルドした実行ファイルは：
- ✅ 通常のユーザーには Python コードが見えない
- ✅ ソースコードの直接閲覧は不可能
- ⚠️ 専門的なツールを使えば逆コンパイル可能

### より高度な保護が必要な場合

1. **PyArmor を使用**（コード暗号化）
```bash
pip install pyarmor
pyarmor gen --pack onefile main.py
```

2. **Nuitka を使用**（ネイティブコンパイル）
```bash
pip install nuitka
python -m nuitka --onefile --windows-disable-console main.py
```

## ビルド設定の詳細

### VRChatSugarChecker.spec の主要な設定

```python
a = Analysis(
    ['main.py'],                    # エントリーポイント
    datas=[                         # 含めるデータファイル
        ('config.example.json', '.'),
        ('submodules', 'submodules'),
    ],
    hiddenimports=['requests'],     # 明示的にインポートするモジュール
)

exe = EXE(
    ...
    name='VRChatSugarChecker',     # 実行ファイル名
    console=True,                   # コンソール表示
    upx=True,                       # UPX圧縮
    icon='icon.ico',                # アイコン（オプション）
)
```

## 自動ビルド（CI/CD）

GitHub Actionsなどで自動ビルドを設定する場合：

```yaml
# .github/workflows/build.yml
name: Build

on: [push]

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - run: pip install -r requirements.txt
      - run: pyinstaller VRChatSugarChecker.spec
      - uses: actions/upload-artifact@v2
        with:
          name: VRChatSugarChecker
          path: dist/
```

## まとめ

- ビルドは `build.bat` または `build.sh` を実行するだけ
- 生成された `dist` フォルダを配布
- ユーザーは Python のインストール不要で実行可能
- ソースコードは見えないため、基本的なコード保護が可能
