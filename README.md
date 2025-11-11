# VRChat Sugar Checker

VRChatの活動を自動記録・通知するツールです。VRChatプレイ中の音声、スクリーンショット、ログを自動保存し、Discord通知やクラウドアップロードができます。

## 主な機能

### 🎮 自動監視
- VRChatの起動/終了を自動検出
- バックグラウンドで目立たないように動作
- Windowsスタートアップに登録可能

### 📢 Discord通知
- VRChat起動/終了の通知
- インスタンス変更の通知
- ユーザー参加/退出の通知（オプション）
- インスタンスリンク付きで簡単参加

### 🎙️ 音声録音
- **VRChat専用音声録音**: C++ネイティブ拡張でVRChatの音声のみをキャプチャ
- Discord等の他アプリの音声は含まれません
- マイク音声も同時録音して自動ミックス
- ワールド毎にファイル自動整理
- WAV形式で高品質録音

### 📸 スクリーンショット
- インスタンス変更時の自動撮影
- 定期的な自動撮影（デフォルト: 3分間隔）
- VRChatウィンドウを自動キャプチャ

### ☁️ ファイルアップロード
- file.io を使用した自動アップロード
- VRChat終了時に自動実行
- ワールド毎にZIP圧縮して整理
- アップロード完了をDiscordに通知

## 動作環境

- **OS**: Windows 10/11 (Build 20438以上を推奨、プロセス固有の音声録音用)
- **Python**: 3.13以上（開発版のみ）
- **その他**: PowerShell、FFmpeg（音声録音を使う場合）
- **開発環境**: Visual Studio Build Tools 2022+ (C++拡張のビルド用)

## インストール

### 方法1: インストーラー版（推奨）

1. [Releases](../../releases) から最新の `VRChatSugarChecker_Setup_*.exe` をダウンロード
2. インストーラーを実行
3. インストール時のオプション選択:
   - ✅ **デスクトップアイコン**: デスクトップにショートカットを作成
   - ✅ **Windows起動時に自動実行**: バックグラウンドで常駐（推奨）
4. インストール完了後、設定ファイルが自動作成されます
5. インストールフォルダの `config.json` を編集して設定を変更

**メリット:**
- 簡単インストール・アンインストール
- スタートアップ登録が自動
- スタートメニューに登録
- 設定ファイルの自動作成

### 方法2: ZIP版（ポータブル）

1. [Releases](../../releases) から最新の `VRChatSugarChecker.zip` をダウンロード
2. 任意のフォルダに解凍
3. `config.example.json` を `config.json` にコピー
4. `config.json` を編集（後述）
5. `VRChatSugarChecker.exe` を実行

**メリット:**
- インストール不要
- USBメモリなどで持ち運び可能
- 複数バージョンの併用が可能

### 方法3: ソースからビルド（開発者向け）

```bash
# リポジトリをクローン
git clone https://github.com/yourusername/VRCSugerChecker.git
cd VRCSugerChecker

# 依存関係をインストール
uv sync

# C++ネイティブ拡張をビルド（初回のみ）
build_native.bat

# 実行可能ファイルをビルド
build.bat           # Windows
# または
./build.sh          # Linux/WSL

# 開発モードで直接実行
uv run python main.py
```

**ビルド要件:**
- Visual Studio Build Tools 2022以上
- Windows SDK 10.0.22000.0以上
- C++コンパイラ (MSVC)

詳細は [CLAUDE.md](CLAUDE.md) を参照してください。

## 設定方法

### Discord WebHook（任意）

Discord通知を使用する場合:

1. Discordサーバーで通知を送信したいチャンネルを開く
2. チャンネル設定 → 連携サービス → ウェブフック → 新しいウェブフック
3. WebHook URLをコピー
4. `config.json` の `discord.webhook_url` に貼り付け

### 設定ファイル（config.json）

主要な設定項目:

```json
{
  "discord": {
    "enabled": true,
    "webhook_url": "YOUR_WEBHOOK_URL",
    "notifications": {
      "vrchat_started": true,
      "vrchat_stopped": true,
      "instance_info": true,
      "instance_changed": true,
      "user_joined": false,
      "user_left": false
    }
  },
  "audio": {
    "enabled": true,
    "auto_start": true,
    "auto_stop": true,
    "retention_days": 7
  },
  "screenshot": {
    "enabled": true,
    "on_instance_change": true,
    "auto_capture": true,
    "auto_capture_interval": 180,
    "retention_days": 7
  },
  "upload": {
    "enabled": true,
    "upload_on_exit": true,
    "daily_upload": true,
    "expires": "1w",
    "cleanup_after_upload": true,
    "notify_discord": true
  }
}
```

#### 設定項目の説明

**Discord通知**
- `enabled`: Discord通知の有効化
- `webhook_url`: Discord WebHook URL
- `notifications.*`: 各種通知の有効/無効

**音声録音**
- `enabled`: 音声録音の有効化
- `auto_start`: VRChat起動時に自動録音開始
- `auto_stop`: VRChat終了時に自動録音停止
- `retention_days`: 録音ファイルの保持期間（日数）

**スクリーンショット**
- `enabled`: スクリーンショット機能の有効化
- `on_instance_change`: インスタンス変更時に撮影
- `auto_capture`: 定期的な自動撮影
- `auto_capture_interval`: 撮影間隔（秒）
- `retention_days`: スクリーンショットの保持期間（日数）

**ファイルアップロード**
- `enabled`: アップロード機能の有効化
- `upload_on_exit`: VRChat終了時にアップロード
- `daily_upload`: 日をまたいだ場合にアップロード
- `expires`: file.io の有効期限（1d/1w/1m/1y）
- `cleanup_after_upload`: アップロード後にファイル削除（ログは除く）
- `notify_discord`: Discord通知を送信

## 使い方

### 通常モード

```bash
# デフォルト設定で起動
python src/main.py

# 設定ファイルを指定
python src/main.py --config config.json

# チェック間隔を変更
python src/main.py --interval 10
```

### バックグラウンドモード

#### インストーラー版の場合
インストール時に「Windows起動時に自動実行」を選択していれば、Windows起動時に自動的にバックグラウンドで実行されます。

手動で実行する場合:
- スタートメニュー → VRChat Sugar Checker → VRChat Sugar Checker (バックグラウンド実行)

#### ZIP版の場合
```bash
# Windowsから
scripts\run_silent.vbs をダブルクリック
```

### スタートアップ登録（ZIP版のみ）

ZIP版でWindows起動時に自動実行したい場合:

```powershell
# インストール
powershell.exe -ExecutionPolicy Bypass -File scripts\install_startup.ps1

# アンインストール
powershell.exe -ExecutionPolicy Bypass -File scripts\uninstall_startup.ps1
```

**注意:** インストーラー版を使用している場合は、この操作は不要です。

## 保存ファイル

すべてのファイルは `logs/` フォルダに保存されます:

```
logs/
├── vrchat_checker.log         # テキストログ（7日間ローテーション）
├── audio/                      # 音声録音
│   └── worldID-20231111_120000.m4a
├── screenshots/                # スクリーンショット
│   └── vrchat_instance_change_20231111_120030.png
└── upload_temp/                # アップロード用一時ファイル
```

## Discord通知の例

### インスタンス情報
```
📊 インスタンス情報

🌍 ワールド: JP Tutorial World
📍 インスタンスID: wrld_xxx:12345~region(jp)
🔗 インスタンスリンク: [VRChatで開く](https://vrchat.com/home/launch?worldId=...)
👥 一緒にいるユーザー (3人)
1. UserName1
2. UserName2
3. UserName3
```

### ファイルアップロード完了
```
📤 ファイルアップロード完了

3個のアーカイブをアップロードしました
合計サイズ: 245.67 MB

📦 1. Tutorial_World
ファイル名: Tutorial_World_20231111.zip
サイズ: 123.45 MB
ダウンロード: file.io
有効期限: 1週間
```

## トラブルシューティング

### Discord通知が届かない
- `config.json` の `webhook_url` を確認
- `discord.enabled` が `true` か確認
- インターネット接続を確認

### 音声録音ができない
- FFmpegがインストールされているか確認
- ステレオミキサーが有効か確認（サウンド設定）
- マイクデバイスが認識されているか確認

### スクリーンショットが撮れない
- VRChatがウィンドウモードで起動しているか確認
- pywin32がインストールされているか確認

### ファイルアップロードが失敗する
- インターネット接続を確認
- file.io のサービス状態を確認
- ファイルサイズが大きすぎないか確認（推奨: 500MB以下）

## セキュリティとプライバシー

### アクセスするデータ
- VRChatのローカルログファイル（読み取りのみ）
- Windowsプロセス情報（VRChat.exe の起動状態）
- 音声入出力デバイス（録音機能使用時）

### データの保存先
- **ローカル**: `logs/` フォルダ
- **Discord**: 通知メッセージ（インスタンス情報、ユーザー情報）
- **file.io**: アップロードされたファイル（1週間後自動削除）

### 注意事項
- 音声録音機能は他のユーザーのプライバシーに関わる場合があります
- 録音する際は一緒にいるユーザーの同意を得ることを推奨します
- アップロードされたファイルのURLは誰でもアクセス可能です

## ライセンス

このプロジェクトは個人利用目的で作成されています。

## 免責事項

- このツールは非公式のサードパーティツールです
- VRChatの利用規約に違反しないよう注意してください
- 使用は自己責任でお願いします

## サポート

- **バグ報告**: [Issues](../../issues)
- **機能リクエスト**: [Issues](../../issues)
- **開発者向けドキュメント**: [DEVELOPMENT.md](DEVELOPMENT.md)
