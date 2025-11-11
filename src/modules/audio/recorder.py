#!/usr/bin/env python3
"""
Audio録音モジュール
VRChatのプロセス音声とマイク音声を別々に録音し、停止時に合成

要件:
- VRChatプロセス音声をAudioSession APIで録音
- マイク音声をsounddeviceで録音
- 録音停止時にFFmpegで非同期合成
- オプションでAI文字起こし
"""
import logging
import subprocess
import threading
import time
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import numpy as np

# Windows Audio Session API
try:
    import comtypes
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioSessionManager2, IAudioSessionEnumerator
    WINDOWS_AUDIO_AVAILABLE = True
except ImportError:
    WINDOWS_AUDIO_AVAILABLE = False
    logging.warning("Windows Audio API（comtypes/pycaw）が利用できません")

# sounddevice for microphone recording
try:
    import sounddevice as sd
    import soundfile as sf
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    logging.warning("sounddeviceが利用できません")

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Audio録音クラス（VRChatプロセス音声 + マイク音声）"""

    def __init__(self, logs_dir: Path, mic_device: Optional[str] = None):
        """
        初期化
        Args:
            logs_dir: ログディレクトリのパス
            mic_device: マイクデバイス名
        """
        self.logs_dir = logs_dir
        self.audio_dir = logs_dir / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        self.mic_device = mic_device
        self.is_recording = False

        # VRChatプロセス音声録音用
        self.vrchat_audio_file: Optional[Path] = None
        self.vrchat_recording_thread: Optional[threading.Thread] = None
        self.vrchat_stop_event = threading.Event()

        # マイク音声録音用
        self.mic_audio_file: Optional[Path] = None
        self.mic_recording_stream = None
        self.mic_audio_data = []

        # 録音情報
        self.current_world_id: Optional[str] = None
        self.current_timestamp: Optional[str] = None
        self.samplerate = 48000  # 48kHz
        self.channels = 2  # ステレオ

    def start_recording(self, world_id: str, instance_id: Optional[str] = None) -> bool:
        """
        録音を開始
        Args:
            world_id: ワールドID
            instance_id: インスタンスID（オプション）
        Returns:
            bool: 録音開始に成功した場合True
        """
        if self.is_recording:
            logger.warning("既に録音中です")
            return False

        if not SOUNDDEVICE_AVAILABLE:
            logger.error("sounddeviceが利用できません")
            return False

        try:
            # ワールドIDから安全なファイル名を生成
            safe_world_id = self._sanitize_filename(world_id)
            self.current_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.current_world_id = world_id

            # VRChatプロセス音声ファイル
            vrchat_filename = f"{safe_world_id}-{self.current_timestamp}_vrchat.wav"
            self.vrchat_audio_file = self.audio_dir / vrchat_filename

            # マイク音声ファイル
            mic_filename = f"{safe_world_id}-{self.current_timestamp}_mic.wav"
            self.mic_audio_file = self.audio_dir / mic_filename

            logger.info(f"録音を開始します: {safe_world_id}")

            # VRChatプロセス音声録音を開始（別スレッド）
            if WINDOWS_AUDIO_AVAILABLE:
                self.vrchat_stop_event.clear()
                self.vrchat_recording_thread = threading.Thread(
                    target=self._record_vrchat_audio,
                    daemon=True
                )
                self.vrchat_recording_thread.start()
            else:
                logger.warning("Windows Audio APIが利用できないため、VRChatプロセス音声は録音されません")

            # マイク音声録音を開始
            self._start_mic_recording()

            self.is_recording = True
            logger.info(f"録音を開始しました")
            return True

        except Exception as e:
            logger.error(f"録音の開始に失敗: {e}")
            import traceback
            traceback.print_exc()
            self.is_recording = False
            return False

    def stop_recording(self) -> bool:
        """
        録音を停止し、ファイルを合成
        Returns:
            bool: 録音停止に成功した場合True
        """
        if not self.is_recording:
            logger.warning("録音していません")
            return False

        try:
            logger.info("録音を停止します")

            # VRChatプロセス音声録音を停止
            if self.vrchat_recording_thread:
                self.vrchat_stop_event.set()
                self.vrchat_recording_thread.join(timeout=5)

            # マイク音声録音を停止
            self._stop_mic_recording()

            self.is_recording = False
            logger.info(f"録音を停止しました")

            # ファイルサイズを確認
            vrchat_size = self.vrchat_audio_file.stat().st_size / (1024 * 1024) if self.vrchat_audio_file and self.vrchat_audio_file.exists() else 0
            mic_size = self.mic_audio_file.stat().st_size / (1024 * 1024) if self.mic_audio_file and self.mic_audio_file.exists() else 0
            logger.info(f"VRChat音声: {vrchat_size:.2f} MB, マイク音声: {mic_size:.2f} MB")

            # FFmpegで合成
            merged_file = self._merge_audio_files()

            # 合成が成功したら元ファイルを削除
            if merged_file and merged_file.exists():
                if self.vrchat_audio_file and self.vrchat_audio_file.exists():
                    self.vrchat_audio_file.unlink()
                if self.mic_audio_file and self.mic_audio_file.exists():
                    self.mic_audio_file.unlink()
                logger.info(f"音声ファイルを合成しました: {merged_file.name}")

            # AI文字起こし（オプション）
            # TODO: 設定で有効化されている場合のみ実行

            self.vrchat_audio_file = None
            self.mic_audio_file = None
            self.current_world_id = None
            return True

        except Exception as e:
            logger.error(f"録音の停止に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _record_vrchat_audio(self):
        """
        VRChatプロセスの音声を録音（Windows Audio Session API使用）
        """
        try:
            # VRChatプロセスを検索
            sessions = AudioUtilities.GetAllSessions()
            vrchat_session = None

            for session in sessions:
                if session.Process and session.Process.name() == "VRChat.exe":
                    vrchat_session = session
                    break

            if not vrchat_session:
                logger.warning("VRChatプロセスが見つかりません。プロセス音声は録音されません")
                return

            # TODO: AudioSession APIでVRChatの音声をキャプチャ
            # 現時点ではWASAPI Loopbackを使用
            logger.info("VRChatプロセス音声録音は未実装です（WASAPI Loopback使用を推奨）")

            # 代替: ステレオミキサーで録音
            # この部分は実装が複雑なため、別途実装が必要

        except Exception as e:
            logger.error(f"VRChatプロセス音声録音中にエラー: {e}")

    def _start_mic_recording(self):
        """
        マイク音声録音を開始（sounddevice使用）
        """
        try:
            # マイクデバイスを検索
            devices = sd.query_devices()
            mic_device_index = None

            if self.mic_device:
                # 指定されたデバイス名で検索
                for i, device in enumerate(devices):
                    if self.mic_device in device['name']:
                        mic_device_index = i
                        break

            if mic_device_index is None:
                # デフォルトの入力デバイスを使用
                mic_device_index = sd.default.device[0]
                logger.info(f"デフォルトマイクデバイスを使用: {devices[mic_device_index]['name']}")
            else:
                logger.info(f"マイクデバイス: {devices[mic_device_index]['name']}")

            # 録音データをリセット
            self.mic_audio_data = []

            # コールバック関数
            def callback(indata, frames, time_info, status):
                if status:
                    logger.warning(f"Recording status: {status}")
                self.mic_audio_data.append(indata.copy())

            # 録音ストリームを開始
            self.mic_recording_stream = sd.InputStream(
                samplerate=self.samplerate,
                channels=self.channels,
                device=mic_device_index,
                callback=callback
            )
            self.mic_recording_stream.start()
            logger.info("マイク録音を開始しました")

        except Exception as e:
            logger.error(f"マイク録音の開始に失敗: {e}")
            import traceback
            traceback.print_exc()

    def _stop_mic_recording(self):
        """
        マイク音声録音を停止し、ファイルに保存
        """
        try:
            if self.mic_recording_stream:
                self.mic_recording_stream.stop()
                self.mic_recording_stream.close()
                logger.info("マイク録音を停止しました")

            # 録音データをファイルに保存
            if self.mic_audio_data and self.mic_audio_file:
                audio_data = np.concatenate(self.mic_audio_data, axis=0)
                sf.write(str(self.mic_audio_file), audio_data, self.samplerate)
                logger.info(f"マイク音声を保存: {self.mic_audio_file.name}")

            self.mic_audio_data = []

        except Exception as e:
            logger.error(f"マイク録音の停止に失敗: {e}")
            import traceback
            traceback.print_exc()

    def _merge_audio_files(self) -> Optional[Path]:
        """
        VRChat音声とマイク音声をFFmpegで合成
        Returns:
            Optional[Path]: 合成されたファイルのパス
        """
        try:
            if not self.current_world_id or not self.current_timestamp:
                return None

            # 合成後のファイル名
            safe_world_id = self._sanitize_filename(self.current_world_id)
            merged_filename = f"{safe_world_id}-{self.current_timestamp}.m4a"
            merged_file = self.audio_dir / merged_filename

            # VRChat音声ファイルが存在しない場合はマイク音声のみ
            if not self.vrchat_audio_file or not self.vrchat_audio_file.exists():
                if self.mic_audio_file and self.mic_audio_file.exists():
                    logger.info("VRChat音声が存在しないため、マイク音声のみ変換します")
                    cmd = [
                        "ffmpeg",
                        "-i", str(self.mic_audio_file),
                        "-c:a", "aac",
                        "-b:a", "192k",
                        "-y",
                        str(merged_file)
                    ]
                else:
                    logger.warning("録音ファイルが存在しません")
                    return None
            # マイク音声ファイルが存在しない場合はVRChat音声のみ
            elif not self.mic_audio_file or not self.mic_audio_file.exists():
                logger.info("マイク音声が存在しないため、VRChat音声のみ変換します")
                cmd = [
                    "ffmpeg",
                    "-i", str(self.vrchat_audio_file),
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-y",
                    str(merged_file)
                ]
            # 両方存在する場合は合成
            else:
                logger.info("VRChat音声とマイク音声を合成します")
                cmd = [
                    "ffmpeg",
                    "-i", str(self.vrchat_audio_file),
                    "-i", str(self.mic_audio_file),
                    "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=longest:dropout_transition=2",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-y",
                    str(merged_file)
                ]

            # FFmpegを実行
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60
            )

            if result.returncode == 0:
                logger.info(f"音声ファイルの合成に成功: {merged_filename}")
                return merged_file
            else:
                logger.error(f"FFmpegエラー: {result.stderr.decode()}")
                return None

        except Exception as e:
            logger.error(f"音声ファイルの合成に失敗: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _sanitize_filename(self, name: str) -> str:
        """
        ファイル名に使用できない文字を削除
        Args:
            name: 元のファイル名
        Returns:
            str: 安全なファイル名
        """
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        name = re.sub(r'\s+', '_', name)
        name = name.strip(' .')
        if len(name) > 200:
            name = name[:200]
        return name

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
        audio_extensions = ['.m4a', '.wav', '.mp3', '.aac']
        deleted_count = 0

        for audio_file in self.audio_dir.iterdir():
            if audio_file.suffix.lower() not in audio_extensions:
                continue

            try:
                file_time = datetime.fromtimestamp(audio_file.stat().st_mtime)
                if file_time < cutoff_time:
                    audio_file.unlink()
                    deleted_count += 1
                    logger.info(f"古い音声ファイルを削除: {audio_file.name}")
            except Exception as e:
                logger.error(f"音声ファイル削除中にエラー: {audio_file.name} - {e}")

        if deleted_count > 0:
            logger.info(f"古い音声ファイルを{deleted_count}個削除しました")
