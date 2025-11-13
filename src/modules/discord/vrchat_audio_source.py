#!/usr/bin/env python3
"""
VRChat Audio Source for Discord.py
VRChatプロセスの音声をリアルタイムでDiscordにストリーミング
"""

import logging
import discord
import numpy as np
import threading
import queue
import time
from typing import Optional

logger = logging.getLogger(__name__)

# C++拡張のインポート
try:
    from audio.wasapi_process_loopback_native import ProcessLoopback
    WASAPI_NATIVE_AVAILABLE = True
except ImportError:
    WASAPI_NATIVE_AVAILABLE = False
    logger.warning("WASAPI Native extension not available")


class VRChatAudioSource(discord.AudioSource):
    """
    VRChatプロセスの音声をDiscordにストリーミングするAudioSource
    discord.pyのPCM形式（48kHz, 16-bit, stereo）に変換して提供
    """

    def __init__(self, vrchat_pid: int, buffer_size: int = 960):
        """
        初期化
        Args:
            vrchat_pid: VRChatプロセスのPID
            buffer_size: バッファサイズ（フレーム数、デフォルト: 960 = 20ms @ 48kHz）
        """
        self.vrchat_pid = vrchat_pid
        self.buffer_size = buffer_size
        self.process_loopback: Optional['ProcessLoopback'] = None
        self.is_running = False
        self.capture_thread: Optional[threading.Thread] = None
        self.audio_queue = queue.Queue(maxsize=50)  # 最大1秒分のバッファ
        self.format_info: Optional[dict] = None

        # Discord.pyの要求フォーマット
        self.target_sample_rate = 48000
        self.target_channels = 2
        self.target_sample_width = 2  # 16-bit

        logger.info(f"VRChatAudioSource initialized for PID: {vrchat_pid}")

    def start(self) -> bool:
        """
        音声キャプチャを開始
        Returns:
            bool: 成功した場合True
        """
        if not WASAPI_NATIVE_AVAILABLE:
            logger.error("WASAPI Native extension not available")
            return False

        try:
            # COM初期化
            import pythoncom
            pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)

            # ProcessLoopbackを初期化
            self.process_loopback = ProcessLoopback(self.vrchat_pid)
            logger.info("ProcessLoopback object created")

            # フォーマット情報を取得
            self.format_info = self.process_loopback.get_format()
            if not self.format_info:
                logger.error("Failed to get audio format")
                return False

            logger.info(f"Audio format: {self.format_info['channels']}ch, "
                       f"{self.format_info['sample_rate']}Hz, "
                       f"{self.format_info['bits_per_sample']}bit")

            # キャプチャスレッドを開始
            self.is_running = True
            self.capture_thread = threading.Thread(
                target=self._capture_loop,
                daemon=True,
                name="VRChatAudioCapture"
            )
            self.capture_thread.start()

            logger.info("VRChat audio capture started")
            return True

        except Exception as e:
            logger.error(f"Failed to start VRChat audio capture: {e}")
            import traceback
            traceback.print_exc()
            return False

    def stop(self):
        """音声キャプチャを停止"""
        self.is_running = False
        if self.capture_thread:
            self.capture_thread.join(timeout=2)

        if self.process_loopback:
            try:
                self.process_loopback.stop()
            except:
                pass

        logger.info("VRChat audio capture stopped")

    def _capture_loop(self):
        """音声キャプチャループ（別スレッドで実行）"""
        try:
            # キャプチャ開始
            if not self.process_loopback.start():
                logger.error("Failed to start ProcessLoopback capture")
                return

            logger.info("Capture loop started")

            while self.is_running:
                try:
                    # 音声データを読み取り（20ms分）
                    audio_data = self.process_loopback.read(self.buffer_size)

                    if audio_data is None or len(audio_data) == 0:
                        time.sleep(0.001)  # 1ms待機
                        continue

                    # numpy配列に変換
                    if self.format_info['bits_per_sample'] == 16:
                        audio_array = np.frombuffer(audio_data, dtype=np.int16)
                    elif self.format_info['bits_per_sample'] == 32:
                        # 32-bit floatを16-bit intに変換
                        audio_float = np.frombuffer(audio_data, dtype=np.float32)
                        audio_array = (audio_float * 32767).astype(np.int16)
                    else:
                        logger.warning(f"Unsupported bit depth: {self.format_info['bits_per_sample']}")
                        continue

                    # リサンプリング・チャンネル変換
                    converted = self._convert_audio(audio_array)

                    if converted is not None and len(converted) > 0:
                        # キューに追加（フルなら古いデータを破棄）
                        try:
                            self.audio_queue.put_nowait(converted.tobytes())
                        except queue.Full:
                            # キューがフルの場合、古いデータを1つ破棄して追加
                            try:
                                self.audio_queue.get_nowait()
                                self.audio_queue.put_nowait(converted.tobytes())
                            except:
                                pass

                except Exception as e:
                    logger.error(f"Error in capture loop: {e}")
                    time.sleep(0.01)

        except Exception as e:
            logger.error(f"Capture loop error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.process_loopback:
                self.process_loopback.stop()

    def _convert_audio(self, audio_data: np.ndarray) -> Optional[np.ndarray]:
        """
        音声データをDiscord形式に変換
        Args:
            audio_data: 入力音声データ（int16配列）
        Returns:
            変換後の音声データ（48kHz, stereo, int16）
        """
        try:
            src_sample_rate = self.format_info['sample_rate']
            src_channels = self.format_info['channels']

            # チャンネル変換
            if src_channels == 1:
                # モノラル→ステレオ
                audio_data = np.repeat(audio_data, 2)
            elif src_channels == 2:
                # ステレオ→そのまま
                pass
            else:
                # 2チャンネルより多い場合、最初の2チャンネルのみ使用
                audio_data = audio_data.reshape(-1, src_channels)[:, :2].flatten()

            # リサンプリング（必要な場合）
            if src_sample_rate != self.target_sample_rate:
                # 簡易リサンプリング（線形補間）
                src_frames = len(audio_data) // 2
                dst_frames = int(src_frames * self.target_sample_rate / src_sample_rate)

                # インデックスを計算
                src_indices = np.linspace(0, src_frames - 1, dst_frames)

                # ステレオなので2チャンネル分処理
                audio_stereo = audio_data.reshape(-1, 2)
                resampled_l = np.interp(src_indices, np.arange(src_frames), audio_stereo[:, 0])
                resampled_r = np.interp(src_indices, np.arange(src_frames), audio_stereo[:, 1])

                audio_data = np.column_stack((resampled_l, resampled_r)).flatten().astype(np.int16)

            return audio_data

        except Exception as e:
            logger.error(f"Error converting audio: {e}")
            return None

    def read(self) -> bytes:
        """
        Discord.pyから呼ばれるメソッド
        20ms分のPCMデータを返す（48kHz, stereo, 16-bit = 3840 bytes）
        Returns:
            bytes: PCM音声データ
        """
        try:
            # キューからデータを取得（タイムアウト付き）
            audio_bytes = self.audio_queue.get(timeout=0.02)  # 20ms
            return audio_bytes
        except queue.Empty:
            # データがない場合は無音を返す
            return b'\x00' * (self.buffer_size * 2 * 2)  # 960 frames * 2 channels * 2 bytes

    def is_opus(self) -> bool:
        """Opusエンコードされているか（PCMなのでFalse）"""
        return False

    def cleanup(self):
        """クリーンアップ"""
        self.stop()
        logger.info("VRChatAudioSource cleaned up")


def get_vrchat_pid() -> Optional[int]:
    """
    VRChatプロセスのPIDを取得
    Returns:
        Optional[int]: VRChatのPID、見つからない場合None
    """
    try:
        import pythoncom
        from pycaw.pycaw import AudioUtilities

        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)

        sessions = AudioUtilities.GetAllSessions()
        for session in sessions:
            if session.Process and session.Process.name() == "VRChat.exe":
                pid = session.ProcessId
                logger.info(f"Found VRChat process: PID {pid}")
                return pid

        logger.warning("VRChat process not found")
        return None

    except Exception as e:
        logger.error(f"Error getting VRChat PID: {e}")
        return None
