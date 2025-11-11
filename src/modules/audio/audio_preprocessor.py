#!/usr/bin/env python3
"""
音声前処理モジュール
音声ファイルから無音区間とBGMのみの部分を検出・除去してトークンを削減する
"""

import logging
import subprocess
import json
from pathlib import Path
from typing import Optional, Tuple, List
import tempfile
import shutil

logger = logging.getLogger(__name__)


class AudioPreprocessor:
    """音声前処理クラス"""

    def __init__(self):
        """初期化"""
        self.ffmpeg_available = self._check_ffmpeg()
        if not self.ffmpeg_available:
            logger.warning("FFmpegが見つかりません。音声前処理機能は無効です。")

    def _check_ffmpeg(self) -> bool:
        """
        FFmpegが利用可能か確認
        Returns:
            bool: FFmpegが利用可能ならTrue
        """
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                timeout=5
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def detect_silence(self, audio_path: Path, noise_tolerance: float = -50.0,
                      duration: float = 2.0) -> List[Tuple[float, float]]:
        """
        無音区間を検出
        Args:
            audio_path: 音声ファイルのパス
            noise_tolerance: ノイズ閾値（dB、デフォルト: -50dB）
            duration: 無音とみなす最小継続時間（秒、デフォルト: 2秒）
        Returns:
            List[Tuple[float, float]]: 無音区間のリスト [(start, end), ...]
        """
        if not self.ffmpeg_available:
            return []

        try:
            # silencedetect フィルターで無音区間を検出
            cmd = [
                "ffmpeg",
                "-i", str(audio_path),
                "-af", f"silencedetect=noise={noise_tolerance}dB:d={duration}",
                "-f", "null",
                "-"
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            # 標準エラー出力から無音区間を抽出
            silence_ranges = []
            silence_start = None

            for line in result.stderr.split('\n'):
                if 'silence_start:' in line:
                    try:
                        silence_start = float(line.split('silence_start:')[1].strip())
                    except (ValueError, IndexError):
                        continue
                elif 'silence_end:' in line and silence_start is not None:
                    try:
                        silence_end = float(line.split('silence_end:')[1].split('|')[0].strip())
                        silence_ranges.append((silence_start, silence_end))
                        silence_start = None
                    except (ValueError, IndexError):
                        continue

            logger.info(f"Detected {len(silence_ranges)} silence ranges in {audio_path.name}")
            return silence_ranges

        except Exception as e:
            logger.error(f"Error detecting silence: {e}")
            return []

    def get_audio_duration(self, audio_path: Path) -> Optional[float]:
        """
        音声ファイルの長さを取得
        Args:
            audio_path: 音声ファイルのパス
        Returns:
            Optional[float]: 長さ（秒）、取得失敗時はNone
        """
        if not self.ffmpeg_available:
            return None

        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(audio_path)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )

            data = json.loads(result.stdout)
            duration = float(data['format']['duration'])
            return duration

        except Exception as e:
            logger.error(f"Error getting audio duration: {e}")
            return None

    def has_speech(self, audio_path: Path, min_speech_ratio: float = 0.1) -> Tuple[bool, float]:
        """
        音声ファイルに会話が含まれているか判定
        Args:
            audio_path: 音声ファイルのパス
            min_speech_ratio: 最小会話時間の割合（0.0-1.0、デフォルト: 0.1 = 10%）
        Returns:
            Tuple[bool, float]: (会話が含まれているか, 会話時間の割合)
        """
        total_duration = self.get_audio_duration(audio_path)
        if not total_duration:
            logger.warning(f"Could not determine duration of {audio_path.name}, assuming has speech")
            return True, 1.0

        # 無音区間を検出
        silence_ranges = self.detect_silence(audio_path, noise_tolerance=-40.0, duration=2.0)

        # 無音時間の合計
        silence_duration = sum(end - start for start, end in silence_ranges)

        # 会話時間の割合
        speech_duration = total_duration - silence_duration
        speech_ratio = speech_duration / total_duration if total_duration > 0 else 0

        logger.info(f"{audio_path.name}: total={total_duration:.1f}s, "
                   f"speech={speech_duration:.1f}s, ratio={speech_ratio:.2%}")

        has_speech = speech_ratio >= min_speech_ratio
        return has_speech, speech_ratio

    def remove_silence(self, audio_path: Path, output_path: Path = None,
                      noise_tolerance: float = -40.0, duration: float = 1.0) -> Optional[Path]:
        """
        音声ファイルから無音区間を除去
        Args:
            audio_path: 入力音声ファイルのパス
            output_path: 出力音声ファイルのパス（Noneの場合は一時ファイル）
            noise_tolerance: ノイズ閾値（dB、デフォルト: -40dB）
            duration: 無音とみなす最小継続時間（秒、デフォルト: 1秒）
        Returns:
            Optional[Path]: 出力ファイルのパス、失敗時はNone
        """
        if not self.ffmpeg_available:
            logger.warning("FFmpeg not available, skipping silence removal")
            return audio_path

        try:
            if output_path is None:
                # 一時ファイルを作成
                temp_dir = audio_path.parent / "temp"
                temp_dir.mkdir(exist_ok=True)
                output_path = temp_dir / f"preprocessed_{audio_path.name}"

            logger.info(f"Removing silence from {audio_path.name}...")

            # silenceremove フィルターで無音を除去
            cmd = [
                "ffmpeg",
                "-i", str(audio_path),
                "-af", f"silenceremove=start_periods=1:start_duration={duration}:start_threshold={noise_tolerance}dB:"
                       f"stop_periods=-1:stop_duration={duration}:stop_threshold={noise_tolerance}dB",
                "-c:a", "aac",
                "-b:a", "192k",
                "-y",  # 上書き
                str(output_path)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5分
            )

            if result.returncode == 0 and output_path.exists():
                original_size = audio_path.stat().st_size / (1024 * 1024)
                processed_size = output_path.stat().st_size / (1024 * 1024)
                reduction = (1 - processed_size / original_size) * 100 if original_size > 0 else 0

                logger.info(f"Silence removal complete: {original_size:.1f}MB -> {processed_size:.1f}MB "
                          f"(reduced by {reduction:.1f}%)")
                return output_path
            else:
                logger.error(f"FFmpeg failed: {result.stderr}")
                return None

        except Exception as e:
            logger.error(f"Error removing silence: {e}")
            return None

    def should_process(self, audio_path: Path, min_duration: int = 60,
                      min_speech_ratio: float = 0.1) -> Tuple[bool, str]:
        """
        音声ファイルをAI処理すべきか判定
        Args:
            audio_path: 音声ファイルのパス
            min_duration: 最小録音時間（秒、デフォルト: 60秒）
            min_speech_ratio: 最小会話時間の割合（デフォルト: 0.1 = 10%）
        Returns:
            Tuple[bool, str]: (処理すべきか, 理由)
        """
        # ファイルの存在確認
        if not audio_path.exists():
            return False, "File not found"

        # 長さをチェック
        duration = self.get_audio_duration(audio_path)
        if duration is None:
            return True, "Could not determine duration, processing anyway"

        if duration < min_duration:
            return False, f"Too short: {duration:.1f}s < {min_duration}s"

        # 会話の有無をチェック
        has_speech, speech_ratio = self.has_speech(audio_path, min_speech_ratio)
        if not has_speech:
            return False, f"No speech detected: speech ratio {speech_ratio:.2%} < {min_speech_ratio:.2%}"

        return True, f"OK: {duration:.1f}s, speech ratio {speech_ratio:.2%}"

    def preprocess(self, audio_path: Path, remove_original: bool = False) -> Optional[Path]:
        """
        音声ファイルを前処理（無音除去 + 圧縮）
        Args:
            audio_path: 入力音声ファイルのパス
            remove_original: 元のファイルを削除するか
        Returns:
            Optional[Path]: 前処理済みファイルのパス、スキップまたは失敗時はNone
        """
        # 処理すべきかチェック
        should_process, reason = self.should_process(audio_path)
        if not should_process:
            logger.info(f"Skipping {audio_path.name}: {reason}")
            return None

        logger.info(f"Preprocessing {audio_path.name}: {reason}")

        # 無音を除去
        processed_path = self.remove_silence(audio_path)
        if not processed_path:
            logger.warning(f"Failed to preprocess {audio_path.name}, using original")
            return audio_path

        # 元のファイルを削除
        if remove_original and processed_path != audio_path:
            try:
                audio_path.unlink()
                # 処理済みファイルを元の名前にリネーム
                final_path = audio_path.parent / audio_path.name
                shutil.move(str(processed_path), str(final_path))
                logger.info(f"Replaced original file with preprocessed version: {final_path.name}")
                return final_path
            except Exception as e:
                logger.error(f"Error replacing original file: {e}")
                return processed_path

        return processed_path
