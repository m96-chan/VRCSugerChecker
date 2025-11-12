#!/usr/bin/env python3
"""
音声解析モジュール
OpenAI Whisper APIで音声をテキスト化し、GPTで会話内容を分析する
分割音声ファイル（part1, part2, ...）のグループ処理に対応
"""

import logging
import re
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from collections import defaultdict
from openai import OpenAI
import sys

# audio_preprocessor をインポート
sys.path.insert(0, str(Path(__file__).parent.parent / "audio"))
from audio_preprocessor import AudioPreprocessor

logger = logging.getLogger(__name__)


class AudioAnalyzer:
    """音声解析クラス"""

    def __init__(self, api_key: str, transcription_model: str = "whisper-1", analysis_model: str = "gpt-4o",
                 enable_preprocessing: bool = True):
        """
        初期化
        Args:
            api_key: OpenAI APIキー
            transcription_model: 文字起こしモデル（デフォルト: whisper-1）
            analysis_model: 分析モデル（デフォルト: gpt-4o）
            enable_preprocessing: 音声前処理を有効にするか（デフォルト: True）
        """
        self.client = OpenAI(api_key=api_key)
        self.transcription_model = transcription_model
        self.analysis_model = analysis_model
        self.enable_preprocessing = enable_preprocessing
        self.preprocessor = AudioPreprocessor() if enable_preprocessing else None
        logger.info(f"AudioAnalyzer initialized with transcription={transcription_model}, "
                   f"analysis={analysis_model}, preprocessing={enable_preprocessing}")

    def transcribe_audio(self, audio_path: Path, language: str = "ja") -> Optional[str]:
        """
        音声ファイルをテキストに変換
        Args:
            audio_path: 音声ファイルのパス
            language: 言語コード（デフォルト: ja）
        Returns:
            Optional[str]: 文字起こし結果（失敗時はNone）
        """
        try:
            if not audio_path.exists():
                logger.error(f"Audio file not found: {audio_path}")
                return None

            logger.info(f"Transcribing audio: {audio_path.name}")

            with open(audio_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model=self.transcription_model,
                    file=audio_file,
                    language=language,
                    response_format="text"
                )

            logger.info(f"Transcription completed: {len(transcript)} characters")
            logger.debug(f"Transcript preview: {transcript[:200]}...")

            return transcript

        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            return None

    def analyze_conversation(self, transcript: str) -> Dict[str, any]:
        """
        文字起こしテキストから会話内容を分析
        Args:
            transcript: 文字起こしテキスト
        Returns:
            Dict: 分析結果
                {
                    'topics': List[str],           # トピック一覧
                    'summary': str,                # 会話内容の概要
                    'decisions': Optional[List[str]],  # 決めたこと（なければNone）
                    'promises': Optional[List[str]],   # 約束したこと（なければNone）
                    'error': Optional[str]         # エラーメッセージ
                }
        """
        try:
            if not transcript:
                return {
                    'topics': [],
                    'summary': '',
                    'decisions': None,
                    'promises': None,
                    'error': 'Empty transcript'
                }

            logger.info(f"Analyzing conversation ({len(transcript)} characters)")

            # GPTで会話内容を分析
            response = self.client.chat.completions.create(
                model=self.analysis_model,
                messages=[
                    {
                        "role": "system",
                        "content": """あなたは会話内容を分析する専門家です。
与えられた会話の文字起こしテキストから、以下の情報を抽出してください：

1. トピック: 会話で話題になったテーマ（3〜5個程度、簡潔に）
2. 会話内容の概要: 全体的な内容を100〜200文字程度で要約
3. 決めたこと: 会話の中で決定された事項（複数可、なければnull）
4. 約束したこと: 会話の中で約束された事項（複数可、なければnull）

回答は以下のJSON形式で出力してください：
{
  "topics": ["トピック1", "トピック2", "トピック3"],
  "summary": "会話内容の概要（100〜200文字）",
  "decisions": ["決定事項1", "決定事項2"] または null,
  "promises": ["約束事項1", "約束事項2"] または null
}

注意：
- 決めたことや約束したことがない場合は、そのフィールドをnullにする
- 日本語で出力する
- JSONフォーマットを厳守する"""
                    },
                    {
                        "role": "user",
                        "content": f"以下の会話を分析してください：\n\n{transcript}"
                    }
                ],
                max_tokens=1000,
                temperature=0.3,
            )

            # レスポンスを解析
            content = response.choices[0].message.content
            logger.debug(f"API response: {content}")

            # JSONコードブロックを除去（```json ... ```で囲まれている場合）
            import json
            import re

            # ```json ... ``` または ``` ... ``` を除去
            if content.strip().startswith('```'):
                # コードブロックを除去
                content = re.sub(r'^```(?:json)?\s*\n', '', content.strip(), flags=re.MULTILINE)
                content = re.sub(r'\n```\s*$', '', content.strip(), flags=re.MULTILINE)
                logger.debug(f"Removed code block markers, cleaned content: {content[:100]}...")

            result = json.loads(content)

            # 必須フィールドの検証
            if not all(key in result for key in ['topics', 'summary', 'decisions', 'promises']):
                raise ValueError("Invalid response format from API")

            result['error'] = None
            logger.info(f"Analysis result: {len(result['topics'])} topics, "
                       f"{len(result['decisions']) if result['decisions'] else 0} decisions, "
                       f"{len(result['promises']) if result['promises'] else 0} promises")

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse API response as JSON: {e}")
            logger.error(f"Response content: {content}")
            return {
                'topics': [],
                'summary': 'APIレスポンスの解析に失敗しました',
                'decisions': None,
                'promises': None,
                'error': f'JSON parse error: {str(e)}'
            }

        except Exception as e:
            logger.error(f"Error analyzing conversation: {e}")
            return {
                'topics': [],
                'summary': 'エラーが発生しました',
                'decisions': None,
                'promises': None,
                'error': str(e)
            }

    def process_audio_file(self, audio_path: Path) -> Dict[str, any]:
        """
        音声ファイルを処理（前処理 + 文字起こし + 分析）
        Args:
            audio_path: 音声ファイルのパス
        Returns:
            Dict: 処理結果
                {
                    'transcript': str,             # 文字起こし結果
                    'topics': List[str],           # トピック一覧
                    'summary': str,                # 会話内容の概要
                    'decisions': Optional[List[str]],  # 決めたこと
                    'promises': Optional[List[str]],   # 約束したこと
                    'preprocessed': bool,          # 前処理が実行されたか
                    'skipped': bool,               # スキップされたか
                    'skip_reason': Optional[str],  # スキップ理由
                    'error': Optional[str]         # エラーメッセージ
                }
        """
        logger.info(f"Processing audio file: {audio_path.name}")

        # 前処理（有効な場合）
        preprocessed = False
        skipped = False
        skip_reason = None
        actual_audio_path = audio_path

        if self.enable_preprocessing and self.preprocessor:
            # 処理すべきかチェック
            should_process, reason = self.preprocessor.should_process(audio_path)
            if not should_process:
                logger.info(f"Skipping AI analysis: {reason}")
                return {
                    'transcript': '',
                    'topics': [],
                    'summary': '音声分析がスキップされました',
                    'decisions': None,
                    'promises': None,
                    'preprocessed': False,
                    'skipped': True,
                    'skip_reason': reason,
                    'error': None
                }

            # 無音除去
            processed_path = self.preprocessor.preprocess(audio_path, remove_original=False)
            if processed_path and processed_path != audio_path:
                actual_audio_path = processed_path
                preprocessed = True
                logger.info(f"Using preprocessed audio: {actual_audio_path.name}")

        # 文字起こし
        transcript = self.transcribe_audio(actual_audio_path)

        # 前処理で生成した一時ファイルを削除
        if preprocessed and actual_audio_path != audio_path:
            try:
                actual_audio_path.unlink()
                logger.debug(f"Deleted temporary preprocessed file: {actual_audio_path.name}")
            except Exception as e:
                logger.warning(f"Failed to delete temporary file: {e}")

        if not transcript:
            return {
                'transcript': '',
                'topics': [],
                'summary': '音声の文字起こしに失敗しました',
                'decisions': None,
                'promises': None,
                'preprocessed': preprocessed,
                'skipped': False,
                'skip_reason': None,
                'error': 'Transcription failed'
            }

        # 会話内容を分析
        analysis = self.analyze_conversation(transcript)
        analysis['transcript'] = transcript
        analysis['preprocessed'] = preprocessed
        analysis['skipped'] = skipped
        analysis['skip_reason'] = skip_reason

        return analysis

    def batch_process(self, audio_paths: List[Path]) -> Dict[Path, Dict]:
        """
        複数の音声ファイルを一括処理
        Args:
            audio_paths: 音声ファイルパスのリスト
        Returns:
            Dict[Path, Dict]: 音声ファイルパスごとの処理結果
        """
        results = {}
        for audio_path in audio_paths:
            logger.info(f"Processing {audio_path.name}...")
            results[audio_path] = self.process_audio_file(audio_path)

        return results

    @staticmethod
    def group_split_files(audio_paths: List[Path]) -> Dict[str, List[Path]]:
        """
        分割音声ファイルをグループ化

        ファイル名パターン: {world_name}-{timestamp}_part{number}.{ext}
        例: Zone_086-20251113_001549_part1.m4a

        Args:
            audio_paths: 音声ファイルパスのリスト
        Returns:
            Dict[str, List[Path]]: ベース名ごとのファイルリスト（part番号順）
        """
        # ファイル名パターン: {base_name}_part{number}.{ext}
        pattern = re.compile(r'^(.+)_part(\d+)\.[^.]+$')

        groups = defaultdict(list)

        for audio_path in audio_paths:
            match = pattern.match(audio_path.name)
            if match:
                base_name = match.group(1)  # world_name-timestamp
                part_number = int(match.group(2))
                groups[base_name].append((part_number, audio_path))
            else:
                # part番号がない単一ファイルは独自のグループ
                groups[audio_path.stem].append((1, audio_path))

        # part番号順にソート
        sorted_groups = {}
        for base_name, files in groups.items():
            files.sort(key=lambda x: x[0])  # part番号でソート
            sorted_groups[base_name] = [path for _, path in files]

        return sorted_groups

    def process_split_audio_group(self, audio_paths: List[Path]) -> Dict[str, any]:
        """
        分割音声ファイルのグループを処理

        各partを個別に文字起こしし、最後に統合して分析

        Args:
            audio_paths: 同じセッションの分割ファイルリスト（順番に並んでいること）
        Returns:
            Dict: 統合された処理結果
                {
                    'transcript': str,             # 統合された文字起こし結果
                    'topics': List[str],           # トピック一覧
                    'summary': str,                # 会話内容の概要
                    'decisions': Optional[List[str]],  # 決めたこと
                    'promises': Optional[List[str]],   # 約束したこと
                    'parts': List[Dict],           # 各partの詳細結果
                    'total_parts': int,            # 総part数
                    'preprocessed': bool,          # 前処理が実行されたか
                    'skipped': bool,               # スキップされたか
                    'skip_reason': Optional[str],  # スキップ理由
                    'error': Optional[str]         # エラーメッセージ
                }
        """
        if not audio_paths:
            return {
                'transcript': '',
                'topics': [],
                'summary': '',
                'decisions': None,
                'promises': None,
                'parts': [],
                'total_parts': 0,
                'preprocessed': False,
                'skipped': False,
                'skip_reason': None,
                'error': 'No audio files provided'
            }

        logger.info(f"Processing split audio group: {len(audio_paths)} parts")

        # 各partを処理
        part_results = []
        combined_transcript = []
        all_preprocessed = True
        any_skipped = False
        skip_reasons = []

        for i, audio_path in enumerate(audio_paths, 1):
            logger.info(f"Processing part {i}/{len(audio_paths)}: {audio_path.name}")

            # 前処理とスキップチェック
            preprocessed = False
            skipped = False
            skip_reason = None
            actual_audio_path = audio_path

            if self.enable_preprocessing and self.preprocessor:
                # 処理すべきかチェック
                should_process, reason = self.preprocessor.should_process(audio_path)
                if not should_process:
                    logger.info(f"Part {i} skipped: {reason}")
                    skipped = True
                    skip_reason = reason
                    any_skipped = True
                    skip_reasons.append(f"Part {i}: {reason}")
                    continue

                # 無音除去
                processed_path = self.preprocessor.preprocess(audio_path, remove_original=False)
                if processed_path and processed_path != audio_path:
                    actual_audio_path = processed_path
                    preprocessed = True
                    logger.info(f"Using preprocessed audio for part {i}: {actual_audio_path.name}")

            # 文字起こし
            transcript = self.transcribe_audio(actual_audio_path)

            # 前処理で生成した一時ファイルを削除
            if preprocessed and actual_audio_path != audio_path:
                try:
                    actual_audio_path.unlink()
                    logger.debug(f"Deleted temporary preprocessed file: {actual_audio_path.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file: {e}")

            if transcript:
                combined_transcript.append(transcript)
                part_results.append({
                    'part': i,
                    'file': audio_path.name,
                    'transcript': transcript,
                    'preprocessed': preprocessed,
                    'skipped': False
                })
            else:
                logger.warning(f"Failed to transcribe part {i}: {audio_path.name}")
                part_results.append({
                    'part': i,
                    'file': audio_path.name,
                    'transcript': '',
                    'preprocessed': preprocessed,
                    'skipped': False,
                    'error': 'Transcription failed'
                })

            all_preprocessed = all_preprocessed and preprocessed

        # 全てスキップされた場合
        if not combined_transcript:
            return {
                'transcript': '',
                'topics': [],
                'summary': '全ての音声ファイルがスキップされました' if any_skipped else '音声の文字起こしに失敗しました',
                'decisions': None,
                'promises': None,
                'parts': part_results,
                'total_parts': len(audio_paths),
                'preprocessed': all_preprocessed,
                'skipped': any_skipped,
                'skip_reason': '; '.join(skip_reasons) if skip_reasons else None,
                'error': 'All parts skipped or transcription failed'
            }

        # 統合された文字起こしテキスト
        full_transcript = '\n\n'.join(combined_transcript)
        logger.info(f"Combined transcript: {len(full_transcript)} characters from {len(combined_transcript)} parts")

        # 会話内容を分析
        analysis = self.analyze_conversation(full_transcript)
        analysis['transcript'] = full_transcript
        analysis['parts'] = part_results
        analysis['total_parts'] = len(audio_paths)
        analysis['preprocessed'] = all_preprocessed
        analysis['skipped'] = any_skipped
        analysis['skip_reason'] = '; '.join(skip_reasons) if skip_reasons else None

        return analysis

    def process_audio_directory(self, audio_dir: Path, pattern: str = "*.m4a") -> Dict[str, Dict]:
        """
        ディレクトリ内の音声ファイルを処理（分割ファイルをグループ化して処理）

        Args:
            audio_dir: 音声ファイルが格納されているディレクトリ
            pattern: ファイル名パターン（デフォルト: *.m4a）
        Returns:
            Dict[str, Dict]: グループ名ごとの処理結果
        """
        if not audio_dir.exists() or not audio_dir.is_dir():
            logger.error(f"Audio directory not found: {audio_dir}")
            return {}

        # ディレクトリ内の音声ファイルを取得
        audio_paths = list(audio_dir.glob(pattern))

        if not audio_paths:
            logger.info(f"No audio files found in {audio_dir}")
            return {}

        logger.info(f"Found {len(audio_paths)} audio files in {audio_dir}")

        # 分割ファイルをグループ化
        groups = self.group_split_files(audio_paths)
        logger.info(f"Grouped into {len(groups)} recording sessions")

        # グループごとに処理
        results = {}
        for group_name, files in groups.items():
            logger.info(f"Processing group '{group_name}' with {len(files)} parts")
            results[group_name] = self.process_split_audio_group(files)

        return results
