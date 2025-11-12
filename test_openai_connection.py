#!/usr/bin/env python3
"""OpenAI API疎通確認スクリプト"""
import json
import sys
from openai import OpenAI

# 標準出力のエンコーディングをUTF-8に設定
sys.stdout.reconfigure(encoding='utf-8')

# config.jsonからAPIキーを読み込み
with open("src/config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

api_key = config["ai"]["openai_api_key"]
client = OpenAI(api_key=api_key)

print("OpenAI API疎通確認中...")
print(f"APIキー: {api_key[:20]}...{api_key[-10:]}")
print()

# 1. モデル一覧取得テスト
print("1. モデル一覧取得テスト:")
try:
    models = client.models.list()
    print(f"[OK] 成功: {len(models.data)}個のモデルが利用可能")
    print(f"  利用可能なWhisperモデル: ", end="")
    whisper_models = [m.id for m in models.data if "whisper" in m.id]
    print(", ".join(whisper_models) if whisper_models else "なし")
except Exception as e:
    print(f"[ERROR] 失敗: {e}")
print()

# 2. Chat Completion APIテスト
print("2. Chat Completion APIテスト:")
try:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hello"}],
        max_tokens=10
    )
    print(f"[OK] 成功: {response.choices[0].message.content}")
except Exception as e:
    print(f"[ERROR] 失敗: {e}")
print()

# 3. Whisper APIテスト（ダミーファイルなしでエンドポイント確認のみ）
print("3. Whisper API エンドポイント確認:")
print(f"  エンドポイント: https://api.openai.com/v1/audio/transcriptions")
print(f"  モデル: whisper-1")
print(f"  ※実際の音声ファイルがある場合のみテスト可能")
print()

print("疎通確認完了")
