# Audio録音機能について

VRChat Sugar Checkerのaudio録音機能の実装ガイドです。

## 現在の実装状況

### 完了している機能

- ✅ `logs/` フォルダの作成と管理
- ✅ `.gitkeep` によるフォルダのGit追跡
- ✅ テキストログの7日間自動ローテーション
- ✅ Audio録音モジュールの基本構造（`submodules/audio/recorder.py`）
- ✅ 設定ファイルへのaudio設定追加（`config.example.json`）

### 未実装（TODO）

- ⚠️ 実際の録音機能（録音ライブラリの統合が必要）
- ⚠️ main.pyへのaudio録音機能の統合

## ファイル構成

```
VRCSugerChecker/
├── logs/
│   ├── .gitkeep
│   ├── vrchat_checker.log          # テキストログ（自動ローテーション）
│   ├── vrchat_checker.log.20250110 # ローテーションされたログ
│   └── vrchat_audio_*.wav          # 録音ファイル（予定）
└── submodules/
    └── audio/
        ├── __init__.py
        └── recorder.py              # Audio録音クラス
```

## ログローテーション

### テキストログ

- **保存場所**: `logs/vrchat_checker.log`
- **ローテーション**: 毎日真夜中（midnight）
- **保持期間**: 7日間
- **命名規則**: `vrchat_checker.log.YYYYMMDD`
- **実装**: `TimedRotatingFileHandler` を使用

### Audioログ

- **保存場所**: `logs/vrchat_audio_*.wav`（予定）
- **保持期間**: 7日間（設定可能）
- **命名規則**: `vrchat_audio_YYYYMMDD_HHMMSS.wav`
- **自動削除**: `cleanup_old_logs()` 関数で処理

## Audio録音機能の実装方法

現在、`AudioRecorder` クラスは骨格のみが実装されています。
実際に録音機能を使用するには、以下のいずれかの方法で実装する必要があります。

### 方法1: sounddevice + soundfile（推奨）

**利点:**
- クロスプラットフォーム
- シンプルで使いやすい
- NumPyベースで高速

**インストール:**
```bash
pip install sounddevice soundfile numpy
```

**実装例:**
```python
import sounddevice as sd
import soundfile as sf
import numpy as np

def start_recording(self, prefix: str = "vrchat_audio") -> bool:
    # ファイル名を生成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.wav"
    self.current_file = self.logs_dir / filename

    # 録音設定
    samplerate = 44100
    channels = 2

    # 録音開始
    self.recording_data = []

    def callback(indata, frames, time, status):
        self.recording_data.append(indata.copy())

    self.stream = sd.InputStream(
        samplerate=samplerate,
        channels=channels,
        callback=callback
    )
    self.stream.start()
    self.is_recording = True
    return True

def stop_recording(self) -> bool:
    if not self.is_recording:
        return False

    # 録音停止
    self.stream.stop()
    self.stream.close()

    # ファイルに保存
    data = np.concatenate(self.recording_data, axis=0)
    sf.write(self.current_file, data, 44100)

    self.is_recording = False
    return True
```

### 方法2: pyaudio

**利点:**
- 広く使われている
- 詳細な制御が可能

**インストール:**
```bash
pip install pyaudio
```

**注意点:**
- Windows: インストールが複雑な場合がある
- WSL: ALSA設定が必要

### 方法3: ffmpeg（サブプロセス）

**利点:**
- 外部プログラムを使用するため、Pythonライブラリのインストール不要
- 多様なフォーマットに対応

**実装例:**
```python
def start_recording(self, prefix: str = "vrchat_audio") -> bool:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.wav"
    self.current_file = self.logs_dir / filename

    # Windows WASAPI Loopback でシステム音声をキャプチャ
    cmd = [
        "ffmpeg",
        "-f", "dshow",
        "-i", "audio=ステレオ ミキサー",  # デバイス名は環境依存
        "-t", "3600",  # 1時間制限（タイムアウト防止）
        str(self.current_file)
    ]

    self.recording_process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    self.is_recording = True
    return True

def stop_recording(self) -> bool:
    if not self.is_recording or not self.recording_process:
        return False

    # ffmpegプロセスを終了（Ctrl+C相当）
    self.recording_process.terminate()
    self.recording_process.wait(timeout=5)

    self.is_recording = False
    return True
```

## Windowsでのオーディオデバイス設定

### ステレオミキサーを有効にする方法

1. タスクバーの音量アイコンを右クリック
2. 「サウンドの設定」を開く
3. 「サウンド コントロール パネル」を開く
4. 「録音」タブを選択
5. 右クリック → 「無効なデバイスの表示」をチェック
6. 「ステレオ ミキサー」を右クリック → 「有効化」

### 仮想オーディオデバイスの使用

より安定した録音のために、VB-Audio Cable などの仮想オーディオデバイスの使用を推奨します。

- **VB-Audio Virtual Cable**: https://vb-audio.com/Cable/
- **無料版**: 1つの仮想デバイス
- **有料版**: 複数の仮想デバイス

## 設定ファイル（config.json）

```json
{
  "audio": {
    "enabled": false,           // Audio録音の有効/無効
    "device_name": null,        // 録音デバイス名（null=デフォルト）
    "format": "wav",            // 録音フォーマット
    "auto_start": true,         // VRChat起動時に自動録音開始
    "auto_stop": true,          // VRChat終了時に自動録音停止
    "retention_days": 7         // 録音ファイルの保持日数
  },
  "logs": {
    "retention_days": 7,        // ログファイルの保持日数
    "text_logs": true,          // テキストログの有効/無効
    "audio_logs": true          // 音声ログの有効/無効
  }
}
```

## main.pyへの統合方法（TODO）

```python
# グローバル変数に追加
audio_recorder: Optional[AudioRecorder] = None

# main()関数で初期化
from submodules.audio import AudioRecorder

audio_config = config.get("audio", {})
if audio_config.get("enabled", False):
    audio_recorder = AudioRecorder(
        logs_dir=logs_dir,
        device_name=audio_config.get("device_name")
    )
    logger.info("Audio録音が有効になっています")

# start_log_monitoring()に録音開始を追加
def start_log_monitoring():
    # ... 既存のコード ...

    # Audio録音開始
    if audio_recorder and config.get("audio", {}).get("auto_start", False):
        audio_recorder.start_recording()

# stop_log_monitoring()に録音停止を追加
def stop_log_monitoring():
    # Audio録音停止
    if audio_recorder and config.get("audio", {}).get("auto_stop", False):
        audio_recorder.stop_recording()

    # ... 既存のコード ...
```

## 注意事項

### プライバシーとセキュリティ

- 音声録音機能は**プライバシーに関わる**機能です
- 使用する際は、一緒にいるユーザーの同意を得ることを推奨します
- 録音ファイルは適切に管理し、不正なアップロードや共有を避けてください

### ストレージ容量

- WAVフォーマット（非圧縮）の場合、容量が大きくなります
  - ステレオ 44.1kHz 16bit: 約10MB/分
  - 1時間で約600MB
- 長時間の録音を行う場合は、ディスク容量に注意してください
- MP3などの圧縮フォーマットの使用も検討してください

### パフォーマンス

- 録音中はCPU/メモリリソースを消費します
- VRChatのパフォーマンスに影響を与える可能性があります
- 必要に応じて録音品質（サンプリングレート、ビット深度）を調整してください

## 今後の実装予定

1. 録音ライブラリの選定と実装
2. デバイス選択機能
3. 録音フォーマットの選択（WAV, MP3, OGG）
4. 録音品質の設定
5. 録音ファイルの圧縮
6. Discord通知への録音ファイル添付（オプション）
7. 録音ファイルのメタデータ記録（インスタンスID、ワールド名など）
