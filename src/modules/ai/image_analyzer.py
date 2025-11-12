#!/usr/bin/env python3
"""
画像解析モジュール
OpenAI Vision APIを使用して、スクリーンショットに他のアバターが映っているかを判定する
"""

import logging
import base64
from pathlib import Path
from typing import Optional, Dict
from openai import OpenAI

logger = logging.getLogger(__name__)


class ImageAnalyzer:
    """画像解析クラス"""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        """
        初期化
        Args:
            api_key: OpenAI APIキー
            model: 使用するモデル（デフォルト: gpt-4o）
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        logger.info(f"ImageAnalyzer initialized with model: {model}")

    def encode_image(self, image_path: Path) -> str:
        """
        画像をBase64エンコード
        Args:
            image_path: 画像ファイルのパス
        Returns:
            str: Base64エンコードされた画像データ
        """
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def analyze_avatar_presence(self, image_path: Path) -> Dict[str, any]:
        """
        スクリーンショットに他のアバターが映っているかを判定
        Args:
            image_path: 画像ファイルのパス
        Returns:
            Dict: 解析結果
                {
                    'has_other_avatars': bool,  # 他のアバターが映っているか
                    'avatar_count': int,         # 推定アバター数（自分を除く）
                    'confidence': str,           # 確信度 (high/medium/low)
                    'description': str,          # 詳細説明
                    'error': Optional[str]       # エラーメッセージ
                }
        """
        try:
            if not image_path.exists():
                logger.error(f"Image file not found: {image_path}")
                return {
                    'has_other_avatars': False,
                    'avatar_count': 0,
                    'confidence': 'low',
                    'description': 'File not found',
                    'error': 'Image file does not exist'
                }

            logger.info(f"Analyzing image: {image_path.name}")

            # 画像をBase64エンコード
            base64_image = self.encode_image(image_path)

            # OpenAI Vision APIでリクエスト
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": """この画像はVRChatのスクリーンショットです。
以下の質問に答えてください：

1. フェイスミラー（顔を映す鏡）を除いて、自分以外のアバターが映っていますか？
2. 映っている場合、何体くらいのアバターが見えますか？（自分を除く）
3. その判定にどれくらい自信がありますか？（high/medium/low）

回答は以下のJSON形式で出力してください：
{
  "has_other_avatars": true or false,
  "avatar_count": 数値（0以上の整数）,
  "confidence": "high" or "medium" or "low",
  "description": "詳細な説明（日本語で50文字程度）"
}

注意：
- フェイスミラー（自分の顔だけが映っている鏡）は「他のアバター」としてカウントしない
- ワールドの装飾や看板に描かれたキャラクターは「アバター」ではない
- 実際に存在する3Dアバターのみをカウントする"""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500,
                temperature=0.3,
            )

            # レスポンスを解析
            content = response.choices[0].message.content
            logger.debug(f"API response: {content}")

            # JSONとして解析（マークダウンコードブロックを除去）
            import json
            import re

            # マークダウンコードブロック（```json ... ``` または ``` ... ```）を除去
            json_content = content.strip()
            if json_content.startswith('```'):
                # コードブロックの開始を除去
                json_content = re.sub(r'^```(?:json)?\s*\n?', '', json_content)
                # コードブロックの終了を除去
                json_content = re.sub(r'\n?```\s*$', '', json_content)
                json_content = json_content.strip()

            result = json.loads(json_content)

            # 必須フィールドの検証
            if not all(key in result for key in ['has_other_avatars', 'avatar_count', 'confidence', 'description']):
                raise ValueError("Invalid response format from API")

            result['error'] = None
            logger.info(f"Analysis result: has_other_avatars={result['has_other_avatars']}, "
                       f"avatar_count={result['avatar_count']}, confidence={result['confidence']}")

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse API response as JSON: {e}")
            logger.error(f"Response content: {content}")
            return {
                'has_other_avatars': False,
                'avatar_count': 0,
                'confidence': 'low',
                'description': 'APIレスポンスの解析に失敗しました',
                'error': f'JSON parse error: {str(e)}'
            }

        except Exception as e:
            logger.error(f"Error analyzing image: {e}")
            return {
                'has_other_avatars': False,
                'avatar_count': 0,
                'confidence': 'low',
                'description': 'エラーが発生しました',
                'error': str(e)
            }

    def batch_analyze(self, image_paths: list[Path]) -> Dict[Path, Dict]:
        """
        複数の画像を一括解析
        Args:
            image_paths: 画像ファイルパスのリスト
        Returns:
            Dict[Path, Dict]: 画像パスごとの解析結果
        """
        results = {}
        for image_path in image_paths:
            logger.info(f"Analyzing {image_path.name}...")
            results[image_path] = self.analyze_avatar_presence(image_path)

        return results
