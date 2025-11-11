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
- VRChatの音声を自動録音（システム音声 + マイク）
- ワールド毎にファイル自動整理
- m4a形式で高品質録音

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

- **OS**: Windows 10/11
- **Python**: 3.13以上
- **その他**: PowerShell、FFmpeg（音声録音を使う場合）

## インストール

### 1. 実行ファイル版（推奨）

1. [Releases](../../releases) から最新版をダウンロード
2. ZIPファイルを解凍
3. `config.example.json` を `config.json` にコピー
4. `config.json` を編集（後述）
5. `VRChatSugarChecker.exe` を実行

### 2. Python版（開発者向け）

```bash
# リポジトリをクローン
git clone https://github.com/yourusername/VRCSugerChecker.git
cd VRCSugerChecker

# 依存関係をインストール
pip install -r requirements.txt
# または
uv sync

# 実行
python src/main.py
```

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

```bash
# Windowsから
scripts\run_silent.vbs をダブルクリック
```

### スタートアップ登録（推奨）

Windows起動時に自動実行:

```powershell
# インストール
powershell.exe -ExecutionPolicy Bypass -File scripts\install_startup.ps1

# アンインストール
powershell.exe -ExecutionPolicy Bypass -File scripts\uninstall_startup.ps1
```

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
