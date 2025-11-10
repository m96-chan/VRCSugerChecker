#!/usr/bin/env python3
"""
Audio録音モジュール
VRChatの音声を録音する機能

要件:
- 録音開始/停止機能
- logsフォルダに保存
- ファイル名にタイムスタンプを含める
- 7日間の自動削除（main.pyのcleanup_old_logsで処理）
"""
import logging
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Audio録音クラス"""

    def __init__(self, logs_dir: Path, device_name: Optional[str] = None):
        """
        初期化
        Args:
            logs_dir: ログディレクトリのパス
            device_name: 録音デバイス名（Noneの場合はデフォルトデバイス）
        """
        self.logs_dir = logs_dir
        self.device_name = device_name
        self.is_recording = False
        self.recording_process: Optional[subprocess.Popen] = None
        self.recording_thread: Optional[threading.Thread] = None
        self.current_file: Optional[Path] = None

    def start_recording(self, prefix: str = "vrchat_audio") -> bool:
        """
        録音を開始
        Args:
            prefix: ファイル名のプレフィックス
        Returns:
            bool: 録音開始に成功した場合True
        """
        if self.is_recording:
            logger.warning("既に録音中です")
            return False

        try:
            # ファイル名を生成（タイムスタンプ付き）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{prefix}_{timestamp}.wav"
            self.current_file = self.logs_dir / filename

            logger.info(f"録音を開始します: {self.current_file}")

            # TODO: 録音の実装
            # 以下は実装の骨格のみ
            # 実際の録音にはpyaudio, sounddevice, または ffmpegなどを使用する必要があります

            self.is_recording = True
            logger.info("録音を開始しました")
            return True

        except Exception as e:
            logger.error(f"録音の開始に失敗: {e}")
            return False

    def stop_recording(self) -> bool:
        """
        録音を停止
        Returns:
            bool: 録音停止に成功した場合True
        """
        if not self.is_recording:
            logger.warning("録音していません")
            return False

        try:
            logger.info("録音を停止します")

            # TODO: 録音停止の実装

            self.is_recording = False
            logger.info(f"録音を停止しました: {self.current_file}")
            return True

        except Exception as e:
            logger.error(f"録音の停止に失敗: {e}")
            return False

    def get_audio_devices(self) -> list:
        """
        利用可能なオーディオデバイスのリストを取得
        Returns:
            list: デバイスリスト
        """
        # TODO: デバイスリストの取得実装
        # pyaudio または sounddevice を使用
        logger.info("オーディオデバイスのリスト取得機能は未実装です")
        return []

    def cleanup_old_audio_files(self, days: int = 7) -> None:
        """
        古い音声ファイルを削除
        Args:
            days: 保持する日数
        """
        from datetime import timedelta

        if not self.logs_dir.exists():
            return

        cutoff_time = datetime.now() - timedelta(days=days)

        # 音声ファイルの拡張子
        audio_extensions = ['.wav', '.mp3', '.ogg', '.flac']

        for audio_file in self.logs_dir.iterdir():
            if audio_file.suffix.lower() not in audio_extensions:
                continue

            try:
                # ファイルの最終更新日時を取得
                file_time = datetime.fromtimestamp(audio_file.stat().st_mtime)

                # カットオフ時間より古い場合は削除
                if file_time < cutoff_time:
                    audio_file.unlink()
                    logger.info(f"古い音声ファイルを削除: {audio_file.name}")
            except Exception as e:
                logger.error(f"音声ファイル削除中にエラー: {audio_file.name} - {e}")


# 使用例とドキュメント
"""
使用例:

from pathlib import Path
from submodules.audio import AudioRecorder

# 録音インスタンスを作成
logs_dir = Path("./logs")
recorder = AudioRecorder(logs_dir)

# 録音開始
recorder.start_recording(prefix="vrchat_audio")

# ... VRChatプレイ中 ...

# 録音停止
recorder.stop_recording()

# 古いファイルのクリーンアップ
recorder.cleanup_old_audio_files(days=7)


録音実装に必要なライブラリ:

1. pyaudio を使用する場合:
   pip install pyaudio

2. sounddevice を使用する場合:
   pip install sounddevice soundfile

3. ffmpeg を使用する場合:
   システムに ffmpeg をインストール
   pip install ffmpeg-python


推奨実装方法:

Windows環境で VRChat の音声を録音する場合、以下の方法が考えられます:

1. Stereo Mix / WASAPI Loopback を使用
   - Windowsのステレオミキサー機能を使用
   - sounddevice または pyaudio でキャプチャ

2. VB-Audio Cable などの仮想オーディオデバイスを使用
   - より高度な音声ルーティングが可能

3. ffmpeg でシステム音声をキャプチャ
   - dshow (DirectShow) を使用
   - コマンド例: ffmpeg -f dshow -i audio="ステレオ ミキサー" output.wav
"""
