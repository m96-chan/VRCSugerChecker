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

        # 固定サイズ出力のためのバッファ
        self.output_buffer = b''
        self.output_buffer_lock = threading.Lock()

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
            try:
                self.process_loopback.start()
            except Exception as e:
                logger.error(f"Failed to start ProcessLoopback capture: {e}")
                return

            logger.info("Capture loop started")

            # デバッグ用カウンター
            read_count = 0
            error_count = 0

            while self.is_running:
                try:
                    # 音声データを読み取り
                    audio_data = self.process_loopback.read()

                    if audio_data is None or len(audio_data) == 0:
                        time.sleep(0.001)  # 1ms待機
                        continue

                    read_count += 1
                    if read_count <= 3:  # 最初の3回だけログ出力
                        logger.info(f"Read audio data: {len(audio_data)} bytes, format_info says: {self.format_info}")

                    # 実際のフォーマットを検出
                    # C++は16-bit PCMと言っているが、WASAPIは32-bit floatで返す可能性がある

                    # まず32-bit floatとして試す
                    if len(audio_data) % 4 == 0:
                        audio_float = np.frombuffer(audio_data, dtype=np.float32)
                        max_val = np.max(np.abs(audio_float)) if len(audio_float) > 0 else 0
                        has_nan = np.isnan(audio_float).any()
                        has_inf = np.isinf(audio_float).any()

                        if read_count <= 3:
                            logger.info(f"As float32: {len(audio_float)} samples, max_val={max_val:.6f}, has_nan={has_nan}, has_inf={has_inf}")

                        # 有効なfloat32データかチェック（NaN/Infがなく、値が妥当な範囲）
                        if not has_nan and not has_inf and 0 < max_val <= 10.0:
                            # 32-bit floatとして処理
                            audio_array = (audio_float * 32767.0).astype(np.int16)
                            if read_count <= 3:
                                logger.info(f"Confirmed 32-bit float format, converted to int16")
                        else:
                            # 16-bit intとして再解釈
                            audio_array = np.frombuffer(audio_data, dtype=np.int16)
                            if read_count <= 3:
                                logger.info(f"Invalid float32 data (nan={has_nan}, inf={has_inf}, max={max_val:.6f}), using int16")
                    else:
                        # バイト数が4の倍数でない場合は16-bit int
                        audio_array = np.frombuffer(audio_data, dtype=np.int16)
                        if read_count <= 3:
                            logger.info(f"Byte count not divisible by 4, using int16: {len(audio_array)} samples")

                    if read_count <= 3:
                        logger.info(f"Audio array: {len(audio_array)} samples, min={np.min(audio_array)}, max={np.max(audio_array)}")

                    # ステレオの場合、サンプル数が偶数であることを確認
                    if self.format_info['channels'] == 2 and len(audio_array) % 2 != 0:
                        # 奇数の場合は最後のサンプルを削除
                        audio_array = audio_array[:-1]
                        if read_count <= 10:
                            logger.warning(f"Trimmed odd sample count: {len(audio_array) + 1} -> {len(audio_array)}")

                    # 音量チェックと正規化
                    max_amplitude = np.max(np.abs(audio_array))

                    # 振幅が極端に小さい場合の処理
                    if max_amplitude > 0 and max_amplitude < 10:
                        # 振幅が10未満（ほぼ無音）の場合は無音として扱う
                        # ゲインを適用してもノイズを増幅するだけなので処理しない
                        if read_count <= 5:
                            logger.debug(f"Near silence detected (amplitude={max_amplitude}), treating as silence")
                        audio_array = np.zeros_like(audio_array)  # 無音に置き換え
                    elif max_amplitude > 0 and max_amplitude < 100:
                        # 10〜100の範囲：異常に小さいが増幅可能
                        if read_count <= 5:
                            logger.warning(f"Low amplitude detected: {max_amplitude}, applying gain (possible format mismatch)")

                        # 音量を正規化（最大振幅を16000程度に）
                        gain = min(16000.0 / max_amplitude, 1000.0)  # 最大1000倍まで
                        audio_array = (audio_array.astype(np.float32) * gain).astype(np.int16)

                        if read_count <= 5:
                            logger.info(f"Applied gain: {gain:.2f}x, new range: {np.min(audio_array)} to {np.max(audio_array)}")

                    # リサンプリング・チャンネル変換
                    converted = self._convert_audio(audio_array, debug=(read_count <= 3))

                    if converted is not None and len(converted) > 0:
                        if read_count <= 3:
                            logger.info(f"Converted audio: {len(converted)} samples ({len(converted) * 2} bytes), min={np.min(converted)}, max={np.max(converted)}")

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

    def _convert_audio(self, audio_data: np.ndarray, debug: bool = False) -> Optional[np.ndarray]:
        """
        音声データをDiscord形式に変換
        Args:
            audio_data: 入力音声データ（int16配列）
            debug: デバッグログを出力するか
        Returns:
            変換後の音声データ（48kHz, stereo, int16）
        """
        try:
            src_sample_rate = self.format_info['sample_rate']
            src_channels = self.format_info['channels']

            if debug:
                logger.info(f"Convert input: {len(audio_data)} samples, {src_channels}ch, {src_sample_rate}Hz")

            # チャンネル変換
            if src_channels == 1:
                # モノラル→ステレオ
                audio_data = np.repeat(audio_data, 2)
                if debug:
                    logger.info(f"Converted mono to stereo: {len(audio_data)} samples")
            elif src_channels == 2:
                # ステレオ→そのまま
                if debug:
                    logger.info(f"Already stereo: {len(audio_data)} samples")
            else:
                # 2チャンネルより多い場合、最初の2チャンネルのみ使用
                audio_data = audio_data.reshape(-1, src_channels)[:, :2].flatten()
                if debug:
                    logger.info(f"Reduced to stereo from {src_channels}ch: {len(audio_data)} samples")

            # リサンプリング（必要な場合）
            if src_sample_rate != self.target_sample_rate:
                # 簡易リサンプリング（線形補間）
                src_frames = len(audio_data) // 2
                dst_frames = int(src_frames * self.target_sample_rate / src_sample_rate)

                if debug:
                    logger.info(f"Resampling: {src_frames} frames @ {src_sample_rate}Hz -> {dst_frames} frames @ {self.target_sample_rate}Hz")

                # インデックスを計算
                src_indices = np.linspace(0, src_frames - 1, dst_frames)

                # ステレオなので2チャンネル分処理
                audio_stereo = audio_data.reshape(-1, 2)
                resampled_l = np.interp(src_indices, np.arange(src_frames), audio_stereo[:, 0])
                resampled_r = np.interp(src_indices, np.arange(src_frames), audio_stereo[:, 1])

                audio_data = np.column_stack((resampled_l, resampled_r)).flatten().astype(np.int16)

                if debug:
                    logger.info(f"Resampled result: {len(audio_data)} samples ({len(audio_data) // 2} frames)")
            else:
                if debug:
                    logger.info(f"No resampling needed: {src_sample_rate}Hz == {self.target_sample_rate}Hz")

            return audio_data

        except Exception as e:
            logger.error(f"Error converting audio: {e}")
            import traceback
            traceback.print_exc()
            return None

    def read(self) -> bytes:
        """
        Discord.pyから呼ばれるメソッド
        20ms分のPCMデータを返す（48kHz, stereo, 16-bit = 3840 bytes）
        Returns:
            bytes: PCM音声データ
        """
        expected_size = self.buffer_size * 2 * 2  # 960 frames * 2 channels * 2 bytes = 3840

        with self.output_buffer_lock:
            # キューから利用可能なデータをすべてバッファに追加
            try:
                while len(self.output_buffer) < expected_size:
                    audio_bytes = self.audio_queue.get_nowait()
                    self.output_buffer += audio_bytes
            except queue.Empty:
                pass

            # バッファに十分なデータがあれば返す
            if len(self.output_buffer) >= expected_size:
                result = self.output_buffer[:expected_size]
                self.output_buffer = self.output_buffer[expected_size:]
                return result
            else:
                # データが足りない場合は無音でパディング
                result = self.output_buffer + b'\x00' * (expected_size - len(self.output_buffer))
                self.output_buffer = b''
                return result

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
