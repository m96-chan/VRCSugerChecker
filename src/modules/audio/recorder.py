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

# PyAudioWPatch for WASAPI loopback recording
try:
    import pyaudiowpatch as pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError as e:
    PYAUDIO_AVAILABLE = False
    logging.warning(f"PyAudioWPatchが利用できません: {e}")
except Exception as e:
    PYAUDIO_AVAILABLE = False
    logging.warning(f"PyAudioWPatchのインポートエラー: {e}")

# WASAPI Process Loopback (C++ Native Extension)
try:
    from .wasapi_process_loopback_native import ProcessLoopback
    WASAPI_NATIVE_AVAILABLE = True
except ImportError as e:
    WASAPI_NATIVE_AVAILABLE = False
    logging.warning(f"WASAPI Native Extensionが利用できません: {e}")

# WASAPI Process Loopback (direct COM API - fallback)
try:
    from .wasapi_process_loopback import WASAPIProcessLoopback
    WASAPI_PROCESS_LOOPBACK_AVAILABLE = True
except ImportError as e:
    WASAPI_PROCESS_LOOPBACK_AVAILABLE = False
    logging.warning(f"WASAPI Process Loopbackが利用できません: {e}")

# sounddevice for microphone recording
try:
    import sounddevice as sd
    import soundfile as sf
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    logging.warning("sounddeviceが利用できません")

logger = logging.getLogger(__name__)

# ネイティブ拡張の可用性をログに記録
if WASAPI_NATIVE_AVAILABLE:
    logger.info("WASAPI Native Extension (C++)が利用可能です")


class AudioRecorder:
    """Audio録音クラス（VRChatプロセス音声 + マイク音声）"""

    def __init__(self, logs_dir: Path, mic_device: Optional[str] = None, keep_source_files: bool = False, split_interval_seconds: int = 3600):
        """
        初期化
        Args:
            logs_dir: ログディレクトリのパス
            mic_device: マイクデバイス名
            keep_source_files: デバッグ用にwavファイルを残すかどうか
            split_interval_seconds: 録音を自動分割する間隔（秒）
        """
        self.logs_dir = logs_dir
        self.audio_dir = logs_dir / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        self.mic_device = mic_device
        self.keep_source_files = keep_source_files
        self.split_interval_seconds = split_interval_seconds
        self.is_recording = False

        # VRChatプロセス音声録音用
        self.vrchat_audio_file: Optional[Path] = None
        self.vrchat_recording_thread: Optional[threading.Thread] = None
        self.vrchat_stop_event = threading.Event()
        self.vrchat_split_event = threading.Event()  # 分割シグナル

        # マイク音声録音用
        self.mic_audio_file: Optional[Path] = None
        self.mic_recording_stream = None
        self.mic_audio_data = []

        # 録音情報
        self.current_world_id: Optional[str] = None
        self.current_timestamp: Optional[str] = None
        self.current_part_number: int = 1  # 分割ファイルの連番
        self.recording_start_time: Optional[float] = None  # 録音開始時刻
        self.samplerate = 48000  # 48kHz
        self.channels = 2  # ステレオ

        # ProcessLoopbackオブジェクトのキャッシュ（インスタンス変更時の再作成を避ける）
        self._cached_process_loopback = None
        self._cached_vrchat_pid = None
        self._cached_is_process_specific = None
        self._cached_format_info = None

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
            self.current_part_number = 1  # 連番をリセット
            self.recording_start_time = time.time()  # 録音開始時刻を記録

            # VRChatプロセス音声ファイル（連番付き）
            vrchat_filename = f"{safe_world_id}-{self.current_timestamp}_part{self.current_part_number}_vrchat.wav"
            self.vrchat_audio_file = self.audio_dir / vrchat_filename

            # マイク音声ファイル（連番付き）
            mic_filename = f"{safe_world_id}-{self.current_timestamp}_part{self.current_part_number}_mic.wav"
            self.mic_audio_file = self.audio_dir / mic_filename

            logger.info(f"録音を開始します: {safe_world_id} (Part {self.current_part_number})")
            logger.info(f"自動分割間隔: {self.split_interval_seconds}秒")

            # VRChatプロセス音声録音を開始（別スレッド）
            if WASAPI_NATIVE_AVAILABLE or WASAPI_PROCESS_LOOPBACK_AVAILABLE or PYAUDIO_AVAILABLE:
                self.vrchat_stop_event.clear()
                self.vrchat_recording_thread = threading.Thread(
                    target=self._record_vrchat_audio,
                    daemon=True
                )
                self.vrchat_recording_thread.start()
            else:
                logger.warning("音声録音ライブラリが利用できないため、システム音声は録音されません")

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

    def _should_split_recording(self) -> bool:
        """
        録音を分割すべきかチェック
        Returns:
            bool: 分割すべき場合True
        """
        if not self.recording_start_time:
            return False

        elapsed_time = time.time() - self.recording_start_time
        return elapsed_time >= self.split_interval_seconds

    def _split_recording_internal(self) -> bool:
        """
        録音を分割（内部処理）
        現在の録音を保存し、新しいファイルで録音を再開
        Returns:
            bool: 分割に成功した場合True
        """
        try:
            logger.info(f"録音を分割します (Part {self.current_part_number} -> Part {self.current_part_number + 1})")

            # VRChatスレッドに分割シグナルを送信
            self.vrchat_split_event.set()

            # マイク録音を一時停止して保存
            self._stop_mic_recording()

            # 現在のファイルパスを保存（削除用）
            old_vrchat_file = self.vrchat_audio_file
            old_mic_file = self.mic_audio_file

            # 現在のファイルをm4aに変換
            merged_file = self._merge_audio_files()

            # 合成が成功したら元ファイルを削除（デバッグモードでは残す）
            if merged_file and merged_file.exists():
                if not self.keep_source_files:
                    if old_vrchat_file and old_vrchat_file.exists():
                        old_vrchat_file.unlink()
                        logger.debug(f"削除: {old_vrchat_file.name}")
                    if old_mic_file and old_mic_file.exists():
                        old_mic_file.unlink()
                        logger.debug(f"削除: {old_mic_file.name}")
                    logger.info(f"音声ファイルを合成しました (分割): {merged_file.name}")
                else:
                    logger.info(f"音声ファイルを合成しました（デバッグモード: wavファイルを保持）(分割): {merged_file.name}")

            # 連番をインクリメント
            self.current_part_number += 1
            self.recording_start_time = time.time()  # 開始時刻をリセット

            # 新しいファイル名を生成
            safe_world_id = self._sanitize_filename(self.current_world_id)
            vrchat_filename = f"{safe_world_id}-{self.current_timestamp}_part{self.current_part_number}_vrchat.wav"
            self.vrchat_audio_file = self.audio_dir / vrchat_filename

            mic_filename = f"{safe_world_id}-{self.current_timestamp}_part{self.current_part_number}_mic.wav"
            self.mic_audio_file = self.audio_dir / mic_filename

            logger.info(f"新しいファイルで録音を再開: Part {self.current_part_number}")

            # マイク録音を再開
            self._start_mic_recording()

            # VRChatスレッドに分割完了を通知（split_eventをクリア）
            self.vrchat_split_event.clear()

            return True

        except Exception as e:
            logger.error(f"録音の分割に失敗: {e}")
            import traceback
            traceback.print_exc()
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

            # 合成が成功したら元ファイルを削除（デバッグモードでは残す）
            if merged_file and merged_file.exists():
                if not self.keep_source_files:
                    if self.vrchat_audio_file and self.vrchat_audio_file.exists():
                        self.vrchat_audio_file.unlink()
                    if self.mic_audio_file and self.mic_audio_file.exists():
                        self.mic_audio_file.unlink()
                    logger.info(f"音声ファイルを合成しました: {merged_file.name}")
                else:
                    logger.info(f"音声ファイルを合成しました（デバッグモード: wavファイルを保持）: {merged_file.name}")

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
        VRChatプロセスのみの音声を録音（WASAPI直接使用）
        Windows WASAPI COMインターフェースを直接使用してシステム音声をキャプチャ
        """
        # ネイティブ拡張を最優先で使用
        if WASAPI_NATIVE_AVAILABLE:
            self._record_vrchat_audio_native()
            return
        # WASAPI Process Loopbackを次に使用
        elif WASAPI_PROCESS_LOOPBACK_AVAILABLE:
            self._record_vrchat_audio_wasapi()
            return
        elif PYAUDIO_AVAILABLE:
            logger.warning("WASAPI Process Loopbackが利用できません。PyAudioWPatchを使用します")
            self._record_vrchat_audio_pyaudio()
            return
        else:
            logger.error("録音に必要なライブラリが利用できません")
            return

    def _get_vrchat_pid_with_retry(self, max_retries: int = 10, retry_delay: float = 1.0) -> Optional[int]:
        """
        VRChatプロセスのPIDを取得（リトライ機能付き）
        Args:
            max_retries: 最大リトライ回数
            retry_delay: リトライ間の待機時間（秒）
        Returns:
            Optional[int]: VRChatプロセスのPID、見つからない場合はNone
        """
        if not WINDOWS_AUDIO_AVAILABLE:
            return None

        import pythoncom
        import sys

        # COM初期化（ループの外で一度だけ）
        # ActivateAudioInterfaceAsyncはSTAスレッドで呼び出す必要があるため、
        # CoInitializeではなくCoInitializeExを使用
        try:
            pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        except Exception as e:
            logger.error(f"COM初期化エラー: {e}")
            return None

        try:
            from pycaw.pycaw import AudioUtilities

            for attempt in range(1, max_retries + 1):
                try:
                    sessions = AudioUtilities.GetAllSessions()
                    for session in sessions:
                        if session.Process and session.Process.name() == "VRChat.exe":
                            vrchat_pid = session.Process.pid
                            logger.info(f"VRChatプロセスを検出: PID {vrchat_pid} (試行 {attempt}/{max_retries})")
                            return vrchat_pid

                    # 見つからなかった場合
                    if attempt < max_retries:
                        logger.info(f"VRChatプロセスが見つかりません。{retry_delay}秒後に再試行します... (試行 {attempt}/{max_retries})")
                        time.sleep(retry_delay)
                    else:
                        logger.warning(f"VRChatプロセスが見つかりませんでした（{max_retries}回試行）")
                except Exception as e:
                    logger.error(f"VRChatプロセス検出中にエラー (試行 {attempt}/{max_retries}): {e}")
                    if attempt < max_retries:
                        time.sleep(retry_delay)

            return None
        finally:
            # COM終了処理（確実に実行）
            try:
                pythoncom.CoUninitialize()
            except:
                pass

    def _record_vrchat_audio_native(self):
        """
        C++ネイティブ拡張を使用してVRChatプロセスのみを録音
        """
        try:
            # VRChatプロセスのPIDを取得（リトライ付き）
            vrchat_pid = self._get_vrchat_pid_with_retry(max_retries=10, retry_delay=1.0)

            if not vrchat_pid:
                logger.warning("VRChatプロセスが見つかりません")
                return

            # ProcessLoopbackオブジェクトのキャッシュを確認
            process_loopback = None
            is_process_specific = None
            format_info = None

            if self._cached_process_loopback and self._cached_vrchat_pid == vrchat_pid:
                # キャッシュされたオブジェクトを再利用
                logger.info(f"VRChatプロセス (PID: {vrchat_pid}) のみの音声をキャプチャします")
                logger.info("C++拡張を使用してプロセス固有のキャプチャを試みます")
                logger.info("キャッシュされたProcessLoopbackオブジェクトを再利用")
                process_loopback = self._cached_process_loopback
                is_process_specific = self._cached_is_process_specific
                format_info = self._cached_format_info

                # キャッシュから復元した情報をログに出力
                if is_process_specific:
                    logger.info("✓ プロセス固有のキャプチャが有効です（VRChatのみの音声）")
                if format_info:
                    logger.info(f"録音フォーマット: {format_info['channels']}ch, "
                               f"{format_info['sample_rate']}Hz, "
                               f"{format_info['bits_per_sample']}bit")
            else:
                # 新規作成
                logger.info(f"VRChatプロセス (PID: {vrchat_pid}) のみの音声をキャプチャします")
                logger.info("C++拡張を使用してプロセス固有のキャプチャを試みます")
                logger.info("※デバッグ出力を確認するには DebugView (https://learn.microsoft.com/en-us/sysinternals/downloads/debugview) を使用してください")
                try:
                    process_loopback = ProcessLoopback(vrchat_pid)
                    logger.info("ProcessLoopbackオブジェクト作成成功")
                except Exception as e:
                    logger.error(f"ProcessLoopback初期化エラー: {e}")
                    import traceback
                    traceback.print_exc()
                    return

                # プロセス固有のキャプチャが有効かチェック
                try:
                    is_process_specific = process_loopback.is_process_specific()
                    if is_process_specific:
                        logger.info("✓ プロセス固有のキャプチャが有効です（VRChatのみの音声）")
                    else:
                        logger.warning("✗ プロセス固有のキャプチャが失敗しました。システム全体の音声をキャプチャします")
                        # エラーの詳細を取得
                        try:
                            last_error = process_loopback.get_last_error()
                            if last_error:
                                logger.warning(f"  詳細: {last_error}")
                            else:
                                logger.warning("  理由: Windows 10 20H1以降が必要、またはActivateAudioInterfaceAsyncが失敗")
                        except:
                            logger.warning("  理由: Windows 10 20H1以降が必要、またはActivateAudioInterfaceAsyncが失敗")
                except Exception as e:
                    logger.warning(f"プロセス固有チェックエラー: {e}")

                # フォーマット情報を取得
                try:
                    format_info = process_loopback.get_format()
                    if format_info:
                        logger.info(f"録音フォーマット: {format_info['channels']}ch, "
                                   f"{format_info['sample_rate']}Hz, "
                                   f"{format_info['bits_per_sample']}bit")
                    else:
                        logger.warning("フォーマット情報を取得できませんでした")
                except Exception as e:
                    logger.error(f"フォーマット取得エラー: {e}")
                    import traceback
                    traceback.print_exc()
                    return

                # キャッシュに保存
                self._cached_process_loopback = process_loopback
                self._cached_vrchat_pid = vrchat_pid
                self._cached_is_process_specific = is_process_specific
                self._cached_format_info = format_info

            # キャプチャを開始
            try:
                process_loopback.start()
                logger.info("VRChatプロセス音声録音を開始（ネイティブ拡張使用）")
            except Exception as e:
                logger.error(f"キャプチャ開始エラー: {e}")
                import traceback
                traceback.print_exc()
                return

            # 録音データ
            vrchat_audio_data = []

            # 録音ループ
            while not self.vrchat_stop_event.is_set():
                try:
                    # 分割シグナルをチェック
                    if self.vrchat_split_event.is_set():
                        logger.info("VRChat録音: 分割シグナルを検出、現在のデータを保存します")

                        # 現在のデータを保存
                        if vrchat_audio_data and self.vrchat_audio_file and format_info:
                            audio_bytes = b''.join(vrchat_audio_data)
                            if format_info['bits_per_sample'] == 16:
                                audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                            elif format_info['bits_per_sample'] == 32:
                                audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
                            else:
                                logger.error(f"未対応のビット深度: {format_info['bits_per_sample']}")
                                break

                            channels = format_info['channels']
                            if channels > 1 and len(audio_array) >= channels:
                                audio_array = audio_array.reshape(-1, channels)

                            sf.write(str(self.vrchat_audio_file), audio_array, format_info['sample_rate'])
                            logger.info(f"VRChat音声を保存 (分割): {self.vrchat_audio_file.name}")

                        # データをクリアして新しいファイルで再開
                        vrchat_audio_data = []

                        # 分割完了を待つ（新しいファイル名が設定されるまで）
                        while self.vrchat_split_event.is_set() and not self.vrchat_stop_event.is_set():
                            time.sleep(0.1)

                        logger.info("VRChat録音: 新しいファイルで録音を再開します")
                        continue

                    # データを読み取り
                    data = process_loopback.read()
                    if data:
                        vrchat_audio_data.append(data)
                    else:
                        time.sleep(0.01)  # データがない場合は少し待つ
                except Exception as e:
                    if not self.vrchat_stop_event.is_set():
                        logger.warning(f"録音読み取りエラー: {e}")
                    break

            # キャプチャを停止
            process_loopback.stop()

            # 録音データを保存
            if vrchat_audio_data and self.vrchat_audio_file and format_info:
                # バイト列を結合
                audio_bytes = b''.join(vrchat_audio_data)

                # バイト列をnumpy配列に変換
                # WASAPIの32bitは通常float形式
                if format_info['bits_per_sample'] == 16:
                    audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                elif format_info['bits_per_sample'] == 32:
                    # 32bitはfloatとして扱う（WASAPIの標準）
                    audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
                else:
                    logger.error(f"未対応のビット深度: {format_info['bits_per_sample']}")
                    return

                # チャンネル数に合わせてreshape
                channels = format_info['channels']
                if channels > 1 and len(audio_array) >= channels:
                    audio_array = audio_array.reshape(-1, channels)

                # ファイルに保存
                sf.write(str(self.vrchat_audio_file), audio_array, format_info['sample_rate'])
                logger.info(f"VRChat音声を保存: {self.vrchat_audio_file.name}")
                size_mb = self.vrchat_audio_file.stat().st_size / (1024 * 1024)
                logger.info(f"ファイルサイズ: {size_mb:.2f} MB")
            else:
                logger.warning("VRChat音声データが記録されませんでした")

        except Exception as e:
            logger.error(f"ネイティブ拡張録音中にエラー: {e}")
            import traceback
            traceback.print_exc()

    def _record_vrchat_audio_wasapi(self):
        """
        WASAPI COMインターフェースを直接使用して録音
        """
        try:
            # VRChatプロセスのPIDを取得（リトライ付き）
            vrchat_pid = self._get_vrchat_pid_with_retry(max_retries=10, retry_delay=1.0)

            if not vrchat_pid:
                logger.warning("VRChatプロセスが見つかりません")

            # WASAPI Process Loopbackを初期化
            wasapi_loopback = WASAPIProcessLoopback(process_id=vrchat_pid)

            if not wasapi_loopback.initialize():
                logger.error("WASAPI初期化に失敗しました")
                return

            format_info = wasapi_loopback.get_format_info()
            if format_info:
                logger.info(f"録音フォーマット: {format_info['channels']}ch, "
                           f"{format_info['sample_rate']}Hz, "
                           f"{format_info['bits_per_sample']}bit")

            # キャプチャを開始
            if not wasapi_loopback.start_capture():
                logger.error("キャプチャ開始に失敗しました")
                wasapi_loopback.cleanup()
                return

            logger.info("システム音声録音を開始（WASAPI直接使用）")

            # 録音データ
            vrchat_audio_data = []

            # 録音ループ
            while not self.vrchat_stop_event.is_set():
                try:
                    # 分割シグナルをチェック
                    if self.vrchat_split_event.is_set():
                        logger.info("VRChat録音(WASAPI): 分割シグナルを検出、現在のデータを保存します")

                        # 現在のデータを保存
                        if vrchat_audio_data and self.vrchat_audio_file and format_info:
                            audio_bytes = b''.join(vrchat_audio_data)
                            if format_info['bits_per_sample'] == 16:
                                audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                            elif format_info['bits_per_sample'] == 32:
                                audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
                            else:
                                logger.error(f"未対応のビット深度: {format_info['bits_per_sample']}")
                                break

                            channels = format_info['channels']
                            if channels > 1 and len(audio_array) >= channels:
                                audio_array = audio_array.reshape(-1, channels)

                            sf.write(str(self.vrchat_audio_file), audio_array, format_info['sample_rate'])
                            logger.info(f"VRChat音声を保存 (分割): {self.vrchat_audio_file.name}")

                        # データをクリアして新しいファイルで再開
                        vrchat_audio_data = []

                        # 分割完了を待つ
                        while self.vrchat_split_event.is_set() and not self.vrchat_stop_event.is_set():
                            time.sleep(0.1)

                        logger.info("VRChat録音(WASAPI): 新しいファイルで録音を再開します")
                        continue

                    # データを読み取り
                    data = wasapi_loopback.read_data()
                    if data:
                        vrchat_audio_data.append(data)
                    else:
                        time.sleep(0.01)  # データがない場合は少し待つ
                except Exception as e:
                    if not self.vrchat_stop_event.is_set():
                        logger.warning(f"録音読み取りエラー: {e}")
                    break

            # キャプチャを停止
            wasapi_loopback.stop_capture()

            # 録音データを保存
            if vrchat_audio_data and self.vrchat_audio_file and format_info:
                # バイト列を結合
                audio_bytes = b''.join(vrchat_audio_data)

                # バイト列をnumpy配列に変換
                # WASAPIの32bitは通常float形式
                if format_info['bits_per_sample'] == 16:
                    audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                elif format_info['bits_per_sample'] == 32:
                    # 32bitはfloatとして扱う（WASAPIの標準）
                    audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
                else:
                    logger.error(f"未対応のビット深度: {format_info['bits_per_sample']}")
                    wasapi_loopback.cleanup()
                    return

                # チャンネル数に合わせてreshape
                channels = format_info['channels']
                if channels > 1 and len(audio_array) >= channels:
                    audio_array = audio_array.reshape(-1, channels)

                # ファイルに保存
                sf.write(str(self.vrchat_audio_file), audio_array, format_info['sample_rate'])
                logger.info(f"VRChat音声を保存: {self.vrchat_audio_file.name}")
                size_mb = self.vrchat_audio_file.stat().st_size / (1024 * 1024)
                logger.info(f"ファイルサイズ: {size_mb:.2f} MB")
            else:
                logger.warning("VRChat音声データが記録されませんでした")

            # クリーンアップ
            wasapi_loopback.cleanup()

        except Exception as e:
            logger.error(f"WASAPI録音中にエラー: {e}")
            import traceback
            traceback.print_exc()

    def _record_vrchat_audio_pyaudio(self):
        """
        PyAudioWPatchを使用して録音（フォールバック）
        """
        try:
            # VRChatプロセスのPIDを取得（リトライ付き）
            vrchat_pid = self._get_vrchat_pid_with_retry(max_retries=10, retry_delay=1.0)

            if not vrchat_pid:
                logger.warning("VRChatプロセスが見つかりません")

            # COM初期化（PyAudioWPatch用）
            import pythoncom
            pythoncom.CoInitialize()

            # PyAudioWPatchでプロセス別ループバックを設定
            p = pyaudio.PyAudio()

            # WASAPIホストAPIインデックスを取得
            wasapi_info = None
            for i in range(p.get_host_api_count()):
                host_api_info = p.get_host_api_info_by_index(i)
                if 'WASAPI' in host_api_info['name']:
                    wasapi_info = host_api_info
                    logger.info(f"WASAPIを検出: {host_api_info['name']}")
                    break

            if not wasapi_info:
                logger.warning("WASAPIが見つかりません")
                p.terminate()
                return

            # Windows 11のプロセスごとのオーディオキャプチャを使用
            # 注: 現在のPyAudioWPatchはプロセス別APIをサポートしていないため、
            # システム全体のループバックを使用（VRChat以外の音声も含まれる）
            try:
                vrchat_loopback_device = p.get_default_wasapi_loopback()

                if vrchat_loopback_device:
                    logger.info(f"ループバックデバイス: {vrchat_loopback_device.get('name', 'Unknown')}")
                    logger.warning("注意: 現在の実装ではシステム音声全体を録音します（VRChatのみの分離は技術的制約により未実装）")
                else:
                    logger.warning("ループバックデバイスが見つかりません")
                    p.terminate()
                    return

            except AttributeError as e:
                logger.error("PyAudioWPatchが必要です。標準PyAudioではWASAPIループバックがサポートされていません")
                logger.info("uv pip install pyaudiowpatch を実行してください")
                p.terminate()
                return
            except Exception as e:
                logger.error(f"ループバックデバイス取得エラー: {e}")
                p.terminate()
                return

            # 録音パラメータ
            channels = vrchat_loopback_device.get('maxInputChannels', 2)
            if channels == 0:
                channels = vrchat_loopback_device.get('maxOutputChannels', 2)

            sample_rate = int(vrchat_loopback_device.get('defaultSampleRate', self.samplerate))

            # sample_rateが高すぎる場合は48kHzに制限
            if sample_rate > self.samplerate:
                sample_rate = self.samplerate

            logger.info(f"録音設定: {channels}チャンネル、{sample_rate}Hz")

            # 録音データ
            vrchat_audio_data = []

            # WASAPIループバックストリームを開く
            try:
                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=channels,
                    rate=sample_rate,
                    input=True,
                    input_device_index=vrchat_loopback_device['index'],
                    frames_per_buffer=1024
                )
            except Exception as e:
                logger.error(f"ループバックストリームを開けません: {e}")
                import traceback
                traceback.print_exc()
                p.terminate()
                return

            stream.start_stream()
            logger.info(f"VRChatプロセス音声録音を開始")

            # 録音ループ
            while not self.vrchat_stop_event.is_set():
                try:
                    # 分割シグナルをチェック
                    if self.vrchat_split_event.is_set():
                        logger.info("VRChat録音(PyAudio): 分割シグナルを検出、現在のデータを保存します")

                        # 現在のデータを保存
                        if vrchat_audio_data and self.vrchat_audio_file:
                            audio_data = np.concatenate(vrchat_audio_data)
                            if channels > 1:
                                audio_data = audio_data.reshape(-1, channels)

                            sf.write(str(self.vrchat_audio_file), audio_data, sample_rate)
                            logger.info(f"VRChat音声を保存 (分割): {self.vrchat_audio_file.name}")

                        # データをクリアして新しいファイルで再開
                        vrchat_audio_data = []

                        # 分割完了を待つ
                        while self.vrchat_split_event.is_set() and not self.vrchat_stop_event.is_set():
                            time.sleep(0.1)

                        logger.info("VRChat録音(PyAudio): 新しいファイルで録音を再開します")
                        continue

                    data = stream.read(1024, exception_on_overflow=False)
                    # int16データをfloat32に変換
                    audio_array = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                    vrchat_audio_data.append(audio_array)
                except Exception as e:
                    if not self.vrchat_stop_event.is_set():
                        logger.warning(f"録音読み取りエラー: {e}")
                    break

            # ストリームを停止
            stream.stop_stream()
            stream.close()
            p.terminate()

            # 録音データを保存
            if vrchat_audio_data and self.vrchat_audio_file:
                audio_data = np.concatenate(vrchat_audio_data)
                # チャンネル数に合わせてreshape
                if channels > 1:
                    audio_data = audio_data.reshape(-1, channels)

                sf.write(str(self.vrchat_audio_file), audio_data, sample_rate)
                logger.info(f"VRChat音声を保存: {self.vrchat_audio_file.name}")
                size_mb = self.vrchat_audio_file.stat().st_size / (1024 * 1024)
                logger.info(f"ファイルサイズ: {size_mb:.2f} MB")
            else:
                logger.warning("VRChat音声データが記録されませんでした")

        except Exception as e:
            logger.error(f"VRChat音声録音中にエラー: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # COM終了処理
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except:
                pass

    def _record_system_audio_fallback(self):
        """
        システム音声全体を録音（フォールバック）
        VRChatプロセスが見つからない場合に使用
        """
        if not PYAUDIO_AVAILABLE:
            return

        try:
            import pythoncom
            pythoncom.CoInitialize()

            p = pyaudio.PyAudio()

            try:
                wasapi_loopback_device = p.get_default_wasapi_loopback()
                if not wasapi_loopback_device:
                    logger.warning("ループバックデバイスが見つかりません")
                    p.terminate()
                    return

                logger.info(f"システム音声全体を録音: {wasapi_loopback_device['name']}")

                channels = wasapi_loopback_device.get('maxOutputChannels', 2)
                sample_rate = int(wasapi_loopback_device.get('defaultSampleRate', self.samplerate))
                if sample_rate > self.samplerate:
                    sample_rate = self.samplerate

                vrchat_audio_data = []

                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=channels,
                    rate=sample_rate,
                    input=True,
                    input_device_index=wasapi_loopback_device['index'],
                    frames_per_buffer=1024
                )

                stream.start_stream()

                while not self.vrchat_stop_event.is_set():
                    try:
                        data = stream.read(1024, exception_on_overflow=False)
                        audio_array = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                        vrchat_audio_data.append(audio_array)
                    except Exception as e:
                        if not self.vrchat_stop_event.is_set():
                            logger.warning(f"録音読み取りエラー: {e}")
                        break

                stream.stop_stream()
                stream.close()
                p.terminate()

                if vrchat_audio_data and self.vrchat_audio_file:
                    audio_data = np.concatenate(vrchat_audio_data)
                    if channels > 1:
                        audio_data = audio_data.reshape(-1, channels)
                    sf.write(str(self.vrchat_audio_file), audio_data, sample_rate)
                    logger.info(f"システム音声を保存: {self.vrchat_audio_file.name}")

            except Exception as e:
                logger.error(f"システム音声録音エラー: {e}")
                p.terminate()

        finally:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except:
                pass

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

            # デバイスの対応チャンネル数を確認
            device_info = devices[mic_device_index]
            max_input_channels = device_info['max_input_channels']

            # デバイスが対応している最大チャンネル数を使用（1 or 2）
            actual_channels = min(self.channels, max_input_channels)
            if actual_channels < self.channels:
                logger.info(f"デバイスはステレオに非対応のため、モノラル録音します（{actual_channels}チャンネル）")

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
                channels=actual_channels,
                device=mic_device_index,
                callback=callback
            )
            self.mic_recording_stream.start()
            logger.info(f"マイク録音を開始しました（{actual_channels}チャンネル、{self.samplerate}Hz）")

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

            # 合成後のファイル名（連番付き）
            safe_world_id = self._sanitize_filename(self.current_world_id)
            merged_filename = f"{safe_world_id}-{self.current_timestamp}_part{self.current_part_number}.m4a"
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
