#!/usr/bin/env python3
"""Whisper API疎通確認スクリプト"""
import json
import sys
import subprocess
from pathlib import Path
from openai import OpenAI

# 標準出力のエンコーディングをUTF-8に設定
sys.stdout.reconfigure(encoding='utf-8')

# config.jsonからAPIキーを読み込み
with open("src/config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

api_key = config["ai"]["openai_api_key"]
client = OpenAI(api_key=api_key)

# テスト用に音声ファイルの最初の5秒を切り出し
audio_dir = Path("logs/audio")
test_audio = audio_dir / "Zone_086-20251113_045105_part1.m4a"
test_clip = Path("test_clip.m4a")

if not test_audio.exists():
    print(f"[ERROR] テスト用音声ファイルが見つかりません: {test_audio}")
    sys.exit(1)

print(f"Whisper API疎通確認中...")
print(f"元ファイル: {test_audio} ({test_audio.stat().st_size / 1024 / 1024:.1f}MB)")
print()

# FFmpegで最初の5秒を切り出し
print("1. テスト用クリップ作成 (最初の5秒):")
try:
    cmd = [
        "ffmpeg", "-y", "-i", str(test_audio),
        "-t", "5",
        "-c", "copy",
        str(test_clip)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[OK] 作成完了: {test_clip.stat().st_size / 1024:.1f}KB")
    else:
        print(f"[ERROR] FFmpegエラー: {result.stderr}")
        sys.exit(1)
except Exception as e:
    print(f"[ERROR] {e}")
    sys.exit(1)
print()

# Whisper APIでトランスクリプション
print("2. Whisper API トランスクリプションテスト:")
try:
    with open(test_clip, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text"
        )
    print(f"[OK] トランスクリプション成功")
    print(f"  結果: {transcript[:100]}..." if len(transcript) > 100 else f"  結果: {transcript}")
except Exception as e:
    print(f"[ERROR] 失敗: {e}")
    import traceback
    traceback.print_exc()
finally:
    # テストファイル削除
    if test_clip.exists():
        test_clip.unlink()
        print(f"\n[INFO] テストファイル削除: {test_clip}")

print("\n疎通確認完了")
