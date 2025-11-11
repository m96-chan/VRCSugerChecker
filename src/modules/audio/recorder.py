#!/usr/bin/env python3
"""
Audio録音モジュール
VRChatの音声を録音する機能

要件:
- 録音開始/停止機能
- logs/audioフォルダに保存
- ワールドIDベースのファイル名
- システム音声とマイク音声の合成録音
- m4a形式で録音
"""
import logging
import subprocess
import threading
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Audio録音クラス（FFmpegベース）"""

    def __init__(self, logs_dir: Path, mic_device: Optional[str] = None):
        """
        初期化
        Args:
            logs_dir: ログディレクトリのパス（logs/audio配下に保存）
            mic_device: マイクデバイス名
        """
        self.logs_dir = logs_dir
        self.audio_dir = logs_dir / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        self.mic_device = mic_device
        self.is_recording = False
        self.recording_process: Optional[subprocess.Popen] = None
        self.current_file: Optional[Path] = None
        self.current_world_id: Optional[str] = None

    def start_recording(self, world_id: str, instance_id: Optional[str] = None) -> bool:
        """
        録音を開始
        Args:
            world_id: ワールドID（wrld_xxxxx形式またはワールド名）
            instance_id: インスタンスID（オプション）
        Returns:
            bool: 録音開始に成功した場合True
        """
        if self.is_recording:
            logger.warning("既に録音中です")
            return False

        try:
            # ワールドIDから安全なファイル名を生成
            safe_world_id = self._sanitize_filename(world_id)

            # タイムスタンプを生成
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # ファイル名: worldID-YYYYMMDD_HHMMSS.m4a
            filename = f"{safe_world_id}-{timestamp}.m4a"
            self.current_file = self.audio_dir / filename
            self.current_world_id = world_id

            logger.info(f"録音を開始します: {filename}")

            # マイクデバイス名を取得
            if not self.mic_device:
                logger.error("マイクデバイスが設定されていません")
                return False

            # FFmpegコマンドを構築
            # -f dshow: DirectShow入力
            # -i audio="device": オーディオデバイス指定
            # -filter_complex amix: 複数音声ソースをミックス
            # -c:a aac: AACコーデック（m4a用）
            # -b:a 192k: ビットレート 192kbps
            cmd = [
                "ffmpeg",
                "-f", "dshow",
                "-i", f"audio=ステレオ ミキサー",  # システム音声
                "-f", "dshow",
                "-i", f"audio={self.mic_device}",  # マイク音声
                "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=longest:dropout_transition=2",
                "-c:a", "aac",
                "-b:a", "192k",
                "-y",  # 上書き
                str(self.current_file)
            ]

            # FFmpegプロセスを起動
            self.recording_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE
            )

            self.is_recording = True
            logger.info(f"録音を開始しました: {filename}")
            return True

        except Exception as e:
            logger.error(f"録音の開始に失敗: {e}")
            self.is_recording = False
            return False

    def stop_recording(self) -> bool:
        """
        録音を停止
        Returns:
            bool: 録音停止に成功した場合True
        """
        if not self.is_recording or not self.recording_process:
            logger.warning("録音していません")
            return False

        try:
            logger.info("録音を停止します")

            # FFmpegプロセスにqコマンド（正常終了）を送信
            try:
                self.recording_process.stdin.write(b'q')
                self.recording_process.stdin.flush()
            except:
                pass

            # プロセスの終了を待つ（最大5秒）
            try:
                self.recording_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # タイムアウトした場合は強制終了
                self.recording_process.terminate()
                self.recording_process.wait(timeout=2)

            self.is_recording = False
            logger.info(f"録音を停止しました: {self.current_file}")

            # ファイルサイズを確認
            if self.current_file and self.current_file.exists():
                size_mb = self.current_file.stat().st_size / (1024 * 1024)
                logger.info(f"録音ファイルサイズ: {size_mb:.2f} MB")

            self.current_file = None
            self.current_world_id = None
            return True

        except Exception as e:
            logger.error(f"録音の停止に失敗: {e}")
            return False

    def _sanitize_filename(self, name: str) -> str:
        """
        ファイル名に使用できない文字を削除
        Args:
            name: 元のファイル名
        Returns:
            str: 安全なファイル名
        """
        # Windows/Linuxで使用できない文字を削除
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        # 連続するスペースを1つに
        name = re.sub(r'\s+', '_', name)
        # 先頭・末尾のスペースやドットを削除
        name = name.strip(' .')
        # 最大長を制限（200文字）
        if len(name) > 200:
            name = name[:200]
        return name

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

    def set_mic_device(self, mic_device: str) -> None:
        """
        マイクデバイスを設定
        Args:
            mic_device: マイクデバイス名
        """
        self.mic_device = mic_device
        logger.info(f"マイクデバイスを設定: {mic_device}")

    def cleanup_old_audio_files(self, days: int = 7) -> None:
        """
        古い音声ファイルを削除
        Args:
            days: 保持する日数
        """
        if not self.audio_dir.exists():
            return

        cutoff_time = datetime.now() - timedelta(days=days)

        # 音声ファイルの拡張子
        audio_extensions = ['.m4a', '.wav', '.mp3', '.aac']

        deleted_count = 0
        for audio_file in self.audio_dir.iterdir():
            if audio_file.suffix.lower() not in audio_extensions:
                continue

            try:
                # ファイルの最終更新日時を取得
                file_time = datetime.fromtimestamp(audio_file.stat().st_mtime)

                # カットオフ時間より古い場合は削除
                if file_time < cutoff_time:
                    audio_file.unlink()
                    deleted_count += 1
                    logger.info(f"古い音声ファイルを削除: {audio_file.name}")
            except Exception as e:
                logger.error(f"音声ファイル削除中にエラー: {audio_file.name} - {e}")

        if deleted_count > 0:
            logger.info(f"古い音声ファイルを{deleted_count}個削除しました")


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
