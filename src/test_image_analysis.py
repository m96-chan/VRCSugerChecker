#!/usr/bin/env python3
"""
画像分析機能のテストスクリプト
"""
import sys
import json
from pathlib import Path

# Config読み込み
config_path = Path('config.json')
if not config_path.exists():
    print("[エラー] config.jsonが見つかりません")
    sys.exit(1)

with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

ai_config = config.get('ai', {})

print("=== AI設定確認 ===")
print(f"ai.enabled: {ai_config.get('enabled')}")
print(f"image_analysis.enabled: {ai_config.get('image_analysis', {}).get('enabled')}")
print()

# APIキーチェック
api_key = ai_config.get('openai_api_key', '')
if not api_key or api_key == 'YOUR_OPENAI_API_KEY':
    print("[エラー] OpenAI APIキーが設定されていません")
    print("config.jsonのai.openai_api_keyに有効なAPIキーを設定してください")
    sys.exit(1)

print(f"[OK] OpenAI APIキー: {api_key[:10]}...")

# AI機能が有効かチェック
if not ai_config.get('enabled'):
    print("[警告] ai.enabledがfalseです。trueに変更してください")
    sys.exit(1)

if not ai_config.get('image_analysis', {}).get('enabled'):
    print("[警告] image_analysis.enabledがfalseです。trueに変更してください")
    sys.exit(1)

print("[OK] AI機能が有効です")
print()

# ImageAnalyzerをインポート
try:
    from modules.ai.image_analyzer import ImageAnalyzer
    print("[OK] ImageAnalyzerモジュールをインポートしました")
except Exception as e:
    print(f"[エラー] ImageAnalyzerのインポートに失敗: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ImageAnalyzerを初期化
try:
    model = ai_config.get('image_analysis', {}).get('model', 'gpt-4o')
    analyzer = ImageAnalyzer(api_key=api_key, model=model)
    print(f"[OK] ImageAnalyzer初期化成功 (model: {model})")
except Exception as e:
    print(f"[エラー] ImageAnalyzer初期化失敗: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("=== スクリーンショット検索 ===")

# スクリーンショットを探す
screenshots_dir = Path('../logs/screenshots')
if not screenshots_dir.exists():
    print(f"[情報] スクリーンショットディレクトリが存在しません: {screenshots_dir}")
    print()
    print("テスト方法:")
    print("1. VRChatを起動してスクリーンショットを撮影")
    print("2. または、テスト用の画像を logs/screenshots/ に配置")
    print("3. このスクリプトを再実行")
    sys.exit(0)

images = list(screenshots_dir.glob('*.png'))
if not images:
    print("[情報] スクリーンショットが見つかりません")
    print()
    print("テスト方法:")
    print("1. VRChatを起動してスクリーンショットを撮影")
    print("2. または、テスト用の画像を logs/screenshots/ に配置")
    print("3. このスクリプトを再実行")
    sys.exit(0)

print(f"[OK] {len(images)}個のスクリーンショットが見つかりました")

# 最新の画像を分析
test_image = images[-1]
print(f"\n分析対象: {test_image.name}")
print("画像分析を実行中...")
print()

try:
    result = analyzer.analyze_avatar_presence(test_image)
    
    print("=== 分析結果 ===")
    print(f"他のアバターが映っているか: {result['has_other_avatars']}")
    print(f"推定アバター数: {result['avatar_count']}体")
    print(f"確信度: {result['confidence']}")
    print(f"説明: {result['description']}")
    
    if result.get('error'):
        print(f"\nエラー: {result['error']}")
    else:
        print("\n[✓] 画像分析成功！")
        
except Exception as e:
    print(f"[✗] 画像分析中にエラーが発生: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
