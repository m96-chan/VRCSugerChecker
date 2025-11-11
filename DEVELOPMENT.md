# VRChat Sugar Checker - 開発者向けドキュメント

このドキュメントは開発者向けの技術情報を提供します。

## 開発環境のセットアップ

### 必要なツール

- **Python**: 3.13以上
- **uv**: Python パッケージマネージャー（推奨）
- **Git**: バージョン管理
- **WSL2**: Windows環境での開発推奨

### 初期セットアップ

```bash
# リポジトリをクローン
git clone https://github.com/yourusername/VRCSugerChecker.git
cd VRCSugerChecker

# 仮想環境の作成と依存関係のインストール
uv sync
# または
python -m venv .venv
source .venv/bin/activate  # Linux/WSL
.venv\Scripts\activate     # Windows
pip install -r requirements.txt

# 設定ファイルの作成
cp config.example.json config.json
```

### 依存関係

主要なライブラリ（`pyproject.toml` 参照）:

- `requests`: HTTP通信（Discord WebHook、file.io）
- `pywin32`: Windows API アクセス
- `pillow`: 画像処理（スクリーンショット）
- FFmpeg: 音声録音（外部プログラム、別途インストール必要）

## プロジェクト構造

```
VRCSugerChecker/
├── src/                          # ソースコード
│   ├── main.py                   # メインエントリーポイント
│   └── modules/                  # 機能モジュール
│       ├── vrc/                  # VRChatログ解析
│       │   └── parse_logs.py
│       ├── discord/              # Discord通知
│       │   ├── __init__.py
│       │   └── webhook.py
│       ├── screenshot/           # スクリーンショット
│       │   ├── __init__.py
│       │   └── capture.py
│       ├── audio/                # 音声録音
│       │   ├── __init__.py
│       │   └── recorder.py
│       └── upload/               # ファイルアップロード
│           ├── __init__.py
│           └── uploader.py
├── scripts/                      # ビルド・デプロイスクリプト
│   ├── build.sh, build.bat       # ビルドスクリプト
│   ├── run_silent.vbs            # サイレント起動
│   ├── install_startup.ps1       # スタートアップ登録
│   └── uninstall_startup.ps1     # スタートアップ解除
├── build/                        # ビルド設定
│   └── VRChatSugarChecker.spec   # PyInstaller設定
├── docs/                         # ドキュメント
│   ├── AUDIO_RECORDING.md
│   ├── BUILD_GUIDE.md
│   └── RELEASE_GUIDE.md
├── logs/                         # 実行時ログ（.gitignoreで除外）
├── config.example.json           # 設定ファイルのテンプレート
├── pyproject.toml                # Python プロジェクト設定
├── requirements.txt              # pip 依存関係
├── uv.lock                       # uv ロックファイル
├── README.md                     # ユーザー向けドキュメント
├── DEVELOPMENT.md                # このファイル
└── CLAUDE.md                     # Claude Code向けガイド
```

## アーキテクチャ

### コアコンポーネント

1. **プロセスモニター** (`src/main.py`)
   - VRChat.exe の起動/終了を監視
   - PowerShell経由でプロセス情報を取得
   - メインループ: `monitor_vrchat_process()`

2. **ログパーサー** (`src/modules/vrc/parse_logs.py`)
   - VRChatログファイルの解析
   - 正規表現パターンマッチング
   - インスタンス変更、ユーザー参加/退出イベントの検出

3. **Discord通知** (`src/modules/discord/webhook.py`)
   - WebHook API経由で通知送信
   - Embed形式でリッチな通知
   - インスタンスリンク生成

4. **スクリーンショット** (`src/modules/screenshot/capture.py`)
   - Win32 API でVRChatウィンドウをキャプチャ
   - PrintWindow または BitBlt
   - 自動キャプチャのバックグラウンドスレッド

5. **音声録音** (`src/modules/audio/recorder.py`)
   - FFmpeg + DirectShow
   - ステレオミキサー + マイクのミキシング
   - ワールド変更時の自動録音切り替え

6. **ファイルアップロード** (`src/modules/upload/uploader.py`)
   - ワールド毎のファイル整理
   - ZIP圧縮
   - file.io API経由でアップロード

### 状態管理

グローバル変数で状態を管理（`src/main.py`）:

```python
discord_webhook: Optional[DiscordWebhook]
screenshot_capture: Optional[ScreenshotCapture]
audio_recorder: Optional[AudioRecorder]
file_uploader: Optional[FileUploader]
config: Dict
last_instance_id: Optional[str]
last_users: Dict[str, str]
last_world_name: Optional[str]
last_upload_date: Optional[str]
```

### イベントフロー

```
VRChat起動
  ↓
start_log_monitoring()
  ├─ ログファイル解析
  ├─ Discord通知（インスタンス情報）
  ├─ 音声録音開始
  └─ スクリーンショット開始
  ↓
update_log_monitoring()（定期実行）
  ├─ インスタンス変更検出 → Discord通知 + スクリーンショット
  ├─ ワールド変更検出 → 音声録音再起動
  └─ ユーザー参加/退出検出 → Discord通知
  ↓
VRChat終了
  ↓
stop_log_monitoring()
  ├─ 音声録音停止
  ├─ スクリーンショット停止
  └─ ファイルアップロード（upload_on_exit: true）
```

## 開発タスク

### ビルド

```bash
# Linux/WSL
./scripts/build.sh

# Windows
scripts\build.bat

# 手動ビルド
cd build
pyinstaller VRChatSugarChecker.spec
```

ビルド成果物: `dist/VRChatSugarChecker.exe`

詳細: [docs/BUILD_GUIDE.md](docs/BUILD_GUIDE.md)

### テスト

構文チェック:
```bash
python -m py_compile src/main.py
find src -name "*.py" -exec python -m py_compile {} \;
```

現在、ユニットテストは未実装。

### コードスタイル

- **フォーマット**: 特定のツール指定なし
- **型ヒント**: Optional で使用
- **ドキュメント**: docstring推奨

### デバッグ

ログレベル設定（`src/main.py:setup_logging()`）:
```python
root_logger.setLevel(logging.DEBUG)  # DEBUG, INFO, WARNING, ERROR
```

ログファイル: `logs/vrchat_checker.log`

## 主要な機能の実装詳細

### VRChatログ解析

パターンマッチング（`src/modules/vrc/parse_logs.py`）:

```python
# インスタンス参加
joining_pattern = re.compile(r'\[Behaviour\] Joining (.+)')

# ユーザー参加
player_joined_pattern = re.compile(r'OnPlayerJoined (.+?) \((usr_[a-f0-9\-]+)\)')

# ユーザー退出
player_left_pattern = re.compile(r'OnPlayerLeft (.+?) \((usr_[a-f0-9\-]+)\)')

# マイクデバイス
microphone_pattern = re.compile(r"uSpeak: SetInputDevice \d+ \(\d+ total\) '(.+?)'")
```

### 音声録音

FFmpegコマンド（`src/modules/audio/recorder.py:start_recording()`）:

```bash
ffmpeg \
  -f dshow -i audio="ステレオ ミキサー" \
  -f dshow -i audio="マイクデバイス名" \
  -filter_complex "[0:a][1:a]amix=inputs=2:duration=longest:dropout_transition=2" \
  -c:a aac -b:a 192k \
  output.m4a
```

### スクリーンショット

Win32 API使用（`src/modules/screenshot/capture.py:_capture_window_win32()`）:

```python
# ウィンドウのデバイスコンテキスト取得
hwndDC = win32gui.GetWindowDC(hwnd)
mfcDC = win32ui.CreateDCFromHandle(hwndDC)
saveDC = mfcDC.CreateCompatibleDC()

# ビットマップ作成
saveBitMap = win32ui.CreateBitmap()
saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)

# PrintWindow でキャプチャ
windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), PW_RENDERFULLCONTENT)

# PIL Image に変換して保存
img = Image.frombuffer('RGB', (width, height), bmpstr, 'raw', 'BGRX', 0, 1)
img.save(path, 'PNG')
```

### ファイルアップロード

ワールド毎のファイル整理（`src/modules/upload/uploader.py`）:

1. 音声ファイル名からワールドID抽出: `worldID-YYYYMMDD_HHMMSS.m4a`
2. スクリーンショットをタイムスタンプで音声ファイルとマッチング（±5分）
3. ログファイルを "logs" グループとして追加
4. ワールド毎にZIP圧縮
5. file.io API でアップロード（リトライ機能付き）
6. アップロード成功後、音声/スクリーンショット削除（ログは保持）

## WSL環境での開発

### VRChatログへのアクセス

WSL から Windows のファイルシステムにアクセス:

```python
# /mnt/c/Users/{username}/AppData/LocalLow/VRChat/VRChat
username = os.getenv('WINDOWS_USER') or os.getenv('USER')
vrchat_log_dir = Path(f"/mnt/c/Users/{username}/AppData/LocalLow/VRChat/VRChat")
```

環境変数設定:
```bash
export WINDOWS_USER=YourWindowsUsername
```

### PowerShell コマンド実行

```python
result = subprocess.run(
    ["powershell.exe", "-Command", "Get-Process -Name VRChat"],
    capture_output=True,
    text=True,
    timeout=5
)
```

## リリースプロセス

詳細: [docs/RELEASE_GUIDE.md](docs/RELEASE_GUIDE.md)

1. バージョン番号更新（`pyproject.toml`）
2. `scripts/build.bat` でビルド
3. `dist/` フォルダをZIP圧縮
4. GitHub Releases で公開
5. 変更履歴を記載

## よくある問題

### pywin32 が WSL でインストールできない

pywin32 は Windows専用。WSL環境では以下を追加:

```toml
[tool.uv]
required-environments = ["win32", "win_amd64"]
```

### ImportError: No module named 'parse_logs'

sys.path の設定を確認:

```python
sys.path.insert(0, str(Path(__file__).parent / "modules" / "vrc"))
sys.path.insert(0, str(Path(__file__).parent / "modules"))
```

### FFmpeg not found

音声録音機能使用時は FFmpeg が必要:

```bash
# Windows
winget install FFmpeg

# または公式サイトからダウンロード
# https://ffmpeg.org/download.html
```

## コントリビューション

1. Fork してブランチ作成
2. 機能追加/バグ修正
3. コミットメッセージは日本語OK
4. Pull Request作成

### コミットメッセージ例

```
機能追加: ファイルアップロード機能の実装

- file.io を使用した自動アップロード
- ワールド毎にZIP圧縮
- Discord通知統合
```

## 参考資料

- [VRChatログ仕様](https://docs.vrchat.com/)
- [Discord Webhook API](https://discord.com/developers/docs/resources/webhook)
- [file.io API](https://www.file.io/)
- [PyInstaller ドキュメント](https://pyinstaller.org/)
- [FFmpeg ドキュメント](https://ffmpeg.org/documentation.html)

## ライセンス

このプロジェクトは個人利用目的で作成されています。
