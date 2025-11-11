#!/usr/bin/env python3
"""
音声解析モジュール
OpenAI Whisper APIで音声をテキスト化し、GPTで会話内容を分析する
"""

import logging
from pathlib import Path
from typing import Optional, Dict, List
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

            # JSONとして解析
            import json
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
