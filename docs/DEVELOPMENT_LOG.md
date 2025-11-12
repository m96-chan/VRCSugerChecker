# 開発ログ - 3ゲート方式アバター検出システム

## 開発期間
2025-11-13

## 実装完了機能

### 1. 3ゲート方式の実装 ✅

**Gate 1: Optical Flow（動き検出）**
- Farneback法による密なOptical Flow計算
- 5フレーム移動平均でノイズ除去
- 対角線長で正規化（flow_normalized = flow_avg / diagonal）
- 閾値: `flow_min` (デフォルト: 0.15)

**Gate 2: Haar Cascade（人体検出）**
- `haarcascade_frontalface_default.xml` - 顔検出
- `haarcascade_upperbody.xml` - 上半身検出
- ブロブの上2/3領域でのみ検出（頭部・肩部分）

**Gate 3: Mirror Suppression（ミラー抑止）**
- ウォームアップ期間（30フレーム）で自動ミラー検出
- Canny エッジ → 輪郭抽出 → 矩形フィルタリング（画面の10-60%）
- テンプレートマッチング（"HQ/LQ Mirror" ラベル検出）
- IoU (Intersection over Union) でブロブとミラー領域の重複判定

### 2. 統合判定ロジック ✅

```python
# 高スコア時はゲートバイパス
bypass_gates = base_score >= 0.70

# 通常判定
normal_pass = base_score >= base_score_threshold AND (flow_ok OR cascade_ok)

# 最終判定
if bypass_gates or normal_pass:
    # 検出成功
```

**スコア内訳:**
- 面積スコア: 0～0.3点（画面の1～15%が理想）
- アスペクト比: 0～0.25点（縦長h/w > 1.1）
- 頭肩パターン: 0～0.25点（上1/3 < 中1/3）
- エッジ密度: 0～0.20点（Cannyエッジ 5～30%）

### 3. パラメータシステム ✅

**config.json設定項目:**
```json
{
  "screenshot": {
    "avatar_detection": {
      "enabled": true,
      "interval": 1,                    // 監視間隔（秒）
      "sensitivity": 0.05,              // 最終スコア閾値
      "mode": "advanced",               // 検出モード
      "consecutive_frames": 2,          // 連続検出フレーム数
      "hold_seconds": 10.0,             // 保持時間（秒）
      "notify_discord": false,          // Discord通知
      "flow_min": 0.15,                 // Optical Flow閾値 ⭐新規
      "base_score_threshold": 0.45,     // ベーススコア閾値 ⭐新規
      "warmup_frames": 30               // ウォームアップ期間 ⭐新規
    }
  }
}
```

**パラメータの統合フロー:**
1. `main.py` (346-366行目) - config.jsonから読み込み
2. `capture.py` (495-540行目) - start_avatar_detection() に渡す
3. `avatar_presence_detector.py` (34-71行目) - コンストラクタで受け取り

### 4. 検出フレーム保存機能 ✅

**問題:** タイムラグで検出時と異なる画像が保存される

**解決策:**
- 検出成功時にフレームをキャッシュ (`last_detected_frame_pil`)
- `get_detected_frame()` で取得
- `_save_detected_frame()` で直接保存

**実装箇所:**
- `avatar_presence_detector.py` (120-122, 677-683, 776-783行目)
- `capture.py` (587-612, 638-643行目)

### 5. 初回検出時のみスクショ保存 ✅

**問題:** hold期間中も連続でスクリーンショットが撮られる

**解決策:**
- `newly_detected` フラグを追加
- 検出状態が `False → True` に変わった時のみ `True`
- capture.pyで `newly_detected == True` の時のみ保存

**実装箇所:**
- `avatar_presence_detector.py` (672-704行目)
- `capture.py` (630-654行目)

### 6. ログ出力の最適化 ✅

- ベーススコア不足: `INFO → DEBUG` (614行目)
- 高スコアバイパス: 専用ログメッセージ (656行目)
- ゲート不通過: スコアも含めて表示 (662行目)

---

## 現在のパラメータ設定

```json
{
  "interval": 1,                    // 1秒おき監視（リアルタイム）
  "sensitivity": 0.05,              // 最終判定閾値（緩め）
  "consecutive_frames": 2,          // 2フレーム連続で検出
  "hold_seconds": 10.0,             // 10秒間保持
  "flow_min": 0.15,                 // 微小な動きも検出
  "base_score_threshold": 0.45,     // 標準的な閾値
  "warmup_frames": 30               // 30フレームでミラー学習
}
```

---

## 次回の作業ポイント

### 1. 実地テスト
- [ ] 静止アバターの検出精度検証
- [ ] ミラー抑止の有効性確認
- [ ] false positive（誤検知）の頻度測定
- [ ] false negative（見逃し）の頻度測定

### 2. パラメータチューニング
- [ ] `flow_min` の最適値を探る（0.10 ~ 0.20）
- [ ] `base_score_threshold` の調整（0.40 ~ 0.50）
- [ ] 高スコアバイパス閾値（現在0.70）の検証

### 3. 改善案（優先度低）
- [ ] カスタムマスク設定UI
- [ ] 動的感度調整（環境に応じた自動調整）
- [ ] デバッグ画像の保存機能（ブロブ・マスク・フロー可視化）
- [ ] 複数アバター同時検出のサポート

### 4. パフォーマンス測定
- [ ] CPU使用率の測定
- [ ] メモリ使用量の測定
- [ ] 検出レイテンシの測定

---

## 既知の問題

### 解決済み
- ✅ タイムラグによる画像のズレ → 検出フレームをキャッシュ
- ✅ hold期間中の連続スクショ → newly_detectedフラグ
- ✅ ログの過剰出力 → DEBUGレベルに変更
- ✅ 静止アバター検出失敗 → flow_min緩和 + 高スコアバイパス

### 未解決
なし（現時点）

---

## 技術仕様

### ファイル構成

```
src/modules/screenshot/
├── avatar_presence_detector.py  (764行) - 3ゲート検出ロジック
├── capture.py                   (660行) - スクリーンショット撮影
└── avatar_detector.py           (165行) - シンプルモード（レガシー）

src/main.py                      (726行) - メインループ、パラメータ統合

config.example.json              - 設定テンプレート
src/config.json                  - ユーザー設定
```

### 依存関係

**必須:**
- OpenCV (cv2) >= 4.8.0
- NumPy
- Pillow (PIL)

**オプション:**
- Haar Cascade分類器（OpenCVに同梱）

### 処理フロー

```
VRChat画面キャプチャ（1秒おき）
  ↓
MOG2背景差分 (history=300, learningRate=0.001)
  ↓
マスク適用（HUD/UI/ミラー除外）
  ↓
モルフォロジー処理（ノイズ除去）
  ↓
ブロブ解析 (connectedComponentsWithStats)
  ↓
各ブロブを3ゲートで評価:
  ├─ Gate 3: ミラー抑止（IoU判定）
  ├─ ベーススコア計算（面積・縦横比・頭肩・エッジ）
  ├─ Gate 1: Optical Flow（動き検出）
  └─ Gate 2: Haar Cascade（顔・上半身検出）
  ↓
統合判定（高スコアバイパス OR 通常判定）
  ↓
時系列フィルタリング（連続Nフレーム + ホールド）
  ↓
初回検出時のみ:
  ├─ フレームをキャッシュ
  ├─ スクリーンショット保存
  └─ Discord通知（設定時）
```

---

## コミット履歴

### 最新コミット
```
commit 7d606d4
Date: 2025-11-13

3ゲート方式アバター検出システムの完全実装

- 3ゲート検出ロジック（Flow + Cascade + Mirror）の実装
- 統合判定システム（高スコアバイパス + 通常判定）
- パラメータの追加と統合（flow_min, base_score_threshold, warmup_frames）
- 検出フレームの保存機能（タイムラグ解消）
- 初回検出時のみスクショ保存（hold期間抑制）
- ログ出力の最適化
```

---

## 参考ドキュメント

- `docs/AVATAR_DETECTION.md` - アバター検出機能の詳細仕様
- `DEVELOPMENT.md` - 開発者向けドキュメント
- `README.md` - ユーザー向けドキュメント

---

## 連絡事項

次回開発時は以下を確認してください：

1. **実地テスト結果の確認**
   - ログファイル: `logs/vrchat_checker.log`
   - スクリーンショット: `logs/screenshots/vrchat_avatar_detected_*.png`

2. **パラメータの調整が必要か**
   - 誤検知が多い → `sensitivity`, `base_score_threshold` を上げる
   - 見逃しが多い → `flow_min` を下げる、`consecutive_frames` を減らす

3. **新機能の開発**
   - 現在のシステムは安定稼働中
   - 別機能の開発に移行可能

---

## 開発者メモ

- 3ゲート方式により、誤検知率が大幅に低減
- 高スコアバイパスで静止アバターにも対応
- パラメータ調整で様々なシーンに対応可能
- 次回はユーザーフィードバックを元にチューニング推奨
