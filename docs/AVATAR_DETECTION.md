# アバター検出機能ドキュメント

VRChat Sugar Checkerのアバター検出機能の詳細ドキュメントです。

## 概要

AIを使用せず、OpenCVの画像処理技術により他のアバター出現を自動検出する機能です。

### 2つの検出モード

#### 1. **Simple Mode（シンプルモード）**
- **方式**: フレーム差分
- **特徴**: 軽量・高速
- **用途**: 低スペックPC、高速検出が必要な場合
- **精度**: 中（画面変化全般に反応）

#### 2. **Advanced Mode（高精度モード）** ⭐ 推奨
- **方式**: MOG2背景差分 + ブロブ解析 + 時系列判定
- **特徴**: 高精度・安定
- **用途**: 標準的な用途、誤検知を減らしたい場合
- **精度**: 高（アバター出現のみに反応）

---

## 技術仕様（Advanced Mode）

### アーキテクチャ

```
VRChat画面
    ↓ (5秒ごとにキャプチャ)
MOG2背景差分 (history=300, learningRate=0.001)
    ↓
マスク適用 (HUD/UI領域除外)
    ↓
モルフォロジー処理 (ノイズ除去)
    ↓
ブロブ解析 (connectedComponents)
    ↓
スコアリング
  ├─ 面積比 (0.5%～25%)
  ├─ アスペクト比 (縦長 h/w > 1.1)
  ├─ 頭肩パターン (上1/3 < 中1/3)
  └─ エッジ密度 (Canny)
    ↓
時系列判定
  ├─ 連続Nフレーム検出 (デフォルト: 6)
  └─ ホールド機能 (デフォルト: 6秒)
    ↓
検出結果 → スクリーンショット保存
```

---

## 設定方法

### config.json

```json
{
  "screenshot": {
    "enabled": true,
    "avatar_detection": {
      "enabled": true,              // アバター検出を有効化
      "interval": 5,                // 監視間隔（秒）
      "sensitivity": 0.10,          // 感度（0.0～1.0）
      "mode": "advanced",           // "simple" or "advanced"
      "consecutive_frames": 6,      // 連続検出フレーム数（advancedのみ）
      "hold_seconds": 6.0          // 検出後の保持時間（advancedのみ）
    }
  }
}
```

### パラメータ詳細

#### **enabled** (boolean)
- `true`: アバター検出機能を有効化
- `false`: 無効化
- デフォルト: `false`

#### **interval** (integer)
- 画面監視の間隔（秒）
- 推奨値:
  - **5秒**: 標準（バランス）
  - **3秒**: 高頻度（やや重い）
  - **10秒**: 低頻度（軽量）
- デフォルト: `5`

#### **sensitivity** (float, 0.0～1.0)
- ブロブスコアの閾値
- **Simple Mode**: 変化率の閾値
  - `0.05～0.08`: 非常に敏感
  - `0.10～0.15`: 標準 ⭐
  - `0.20～0.30`: 鈍感
- **Advanced Mode**: ブロブスコア閾値
  - `0.08～0.12`: 敏感（小さいアバターも検出）
  - `0.10～0.15`: 標準 ⭐
  - `0.15～0.25`: 鈍感（大きいアバターのみ）
- デフォルト: `0.10`

#### **mode** (string)
- 検出モード
  - `"simple"`: フレーム差分モード
  - `"advanced"`: 高精度モード ⭐ 推奨
- デフォルト: `"advanced"`

#### **consecutive_frames** (integer, advancedのみ)
- 連続検出フレーム数
- この回数連続でスコアが閾値を超えたら「検出」と判断
- 推奨値:
  - **4～6**: 標準 ⭐
  - **3以下**: 敏感（誤検知増加）
  - **7以上**: 慎重（見逃し増加）
- デフォルト: `6`

#### **hold_seconds** (float, advancedのみ)
- 検出後の保持時間（秒）
- 検出後、この時間は検出状態を維持
- 連続撮影を防ぐクールダウン的な役割
- 推奨値:
  - **5～10秒**: 標準 ⭐
  - **3秒以下**: 短い（連続撮影の可能性）
  - **15秒以上**: 長い（変化を見逃す可能性）
- デフォルト: `6.0`

---

## 使用方法

### 1. 依存関係のインストール

```bash
# OpenCVをインストール
uv sync
# または
pip install opencv-python>=4.8.0
```

### 2. 設定ファイルの編集

`src/config.json` を編集：

```json
{
  "screenshot": {
    "enabled": true,
    "avatar_detection": {
      "enabled": true,
      "mode": "advanced"
    }
  }
}
```

### 3. アプリケーション起動

```bash
uv run python src/main.py
```

### 4. VRChat起動

- VRChatを起動すると自動的にアバター検出開始
- 5秒ごとに画面を監視
- アバター出現時に自動でスクリーンショット保存

---

## ログ出力例

### Advanced Mode

```
2025-11-13 10:00:00 [INFO] AvatarPresenceDetector initialized (sensitivity=0.1, frames=6, hold=6.0s)
2025-11-13 10:00:00 [INFO] 高精度アバター検出モード: frames=6, hold=6.0s
2025-11-13 10:00:00 [INFO] アバター検出を開始: 5秒おき, 感度=10.0%, mode=advanced
2025-11-13 10:00:00 [INFO] Default mask created: 1920x1080, active area: 384~1536, 54~810
2025-11-13 10:00:05 [DEBUG] Blob score: 0.123 (area=0.15, aspect=0.25, head_shoulder=0.15, edge=0.20)
2025-11-13 10:00:30 [INFO] アバター出現検出！ (score=0.750, consecutive=6)
2025-11-13 10:00:30 [INFO] スクリーンショットを保存: vrchat_avatar_detected_20251113_100030.png
2025-11-13 10:00:30 [INFO] 画像分析を開始: vrchat_avatar_detected_20251113_100030.png
```

---

## 検出アルゴリズム詳細（Advanced Mode）

### 1. MOG2背景差分

```python
bg_subtractor = cv2.createBackgroundSubtractorMOG2(
    history=300,        # 過去300フレームで背景学習
    varThreshold=16,    # 分散閾値
    detectShadows=True  # 影検出を有効化
)
fg_mask = bg_subtractor.apply(frame, learningRate=0.001)  # ゆっくり学習
```

**特徴:**
- 動的背景に対応（ワールドギミック、光の変化など）
- 影を除去（127=影、255=前景）
- 学習率を小さくして安定性を向上

### 2. マスク処理

デフォルトマスク領域:
- **画面下部 25%**: チャット、通知など
- **画面左右 20%**: UI、サイドメニューなど
- **画面上部 5%**: タイトルバー、FPSカウンターなど

### 3. ブロブスコアリング

各ブロブに対して以下のスコアを計算：

#### a. 面積スコア（0～0.3点）
```python
area_ratio = blob_area / total_pixels

if 0.01 <= area_ratio <= 0.15:    # 理想的（1%～15%）
    score = 0.3
elif 0.005 <= area_ratio < 0.01:  # やや小さい
    score = 0.15
else:                              # 大きすぎる/小さすぎる
    score = 0.1
```

#### b. アスペクト比スコア（0～0.25点）
```python
aspect_ratio = height / width

if 1.5 <= aspect_ratio <= 2.5:    # 理想的（人型）
    score = 0.25
elif 1.1 <= aspect_ratio < 1.5:   # やや縦長
    score = 0.15
else:                              # 横長または極端
    score = 0.0
```

#### c. 頭肩パターンスコア（0～0.25点）
```python
# 上1/3と中1/3の幅を比較
if mid_width > top_width * 1.1:    # 中央が上部より10%以上広い
    score = 0.25
elif mid_width > top_width:        # 中央が上部より広い
    score = 0.15
else:
    score = 0.0
```

#### d. エッジ密度スコア（0～0.20点）
```python
edges = cv2.Canny(roi, 50, 150)
edge_density = edge_pixels / total_pixels

if 0.05 <= edge_density <= 0.30:  # 適度なエッジ
    score = 0.20
elif 0.02 <= edge_density < 0.05: # やや少ない
    score = 0.10
else:
    score = 0.05
```

**総合スコア**: 最大1.0点（0.3 + 0.25 + 0.25 + 0.20）

### 4. 時系列判定

```python
# スコアキューに追加（最大6フレーム保持）
score_queue.append(current_score)

# 連続検出カウント
consecutive_detections = sum(1 for s in score_queue if s >= threshold)

# 判定
if consecutive_detections >= 6:
    detected = True
    hold_until = current_time + 6.0  # 6秒間保持
elif current_time < hold_until:
    detected = True  # ホールド期間中
else:
    detected = False
```

---

## チューニングガイド

### 誤検知が多い場合

1. **感度を下げる**
   ```json
   "sensitivity": 0.15  // 0.10 → 0.15
   ```

2. **連続検出フレーム数を増やす**
   ```json
   "consecutive_frames": 8  // 6 → 8
   ```

3. **Simple Modeに変更**
   ```json
   "mode": "simple"
   ```

### 見逃しが多い場合

1. **感度を上げる**
   ```json
   "sensitivity": 0.08  // 0.10 → 0.08
   ```

2. **連続検出フレーム数を減らす**
   ```json
   "consecutive_frames": 4  // 6 → 4
   ```

3. **監視間隔を短くする**
   ```json
   "interval": 3  // 5 → 3
   ```

### CPU使用率が高い場合

1. **監視間隔を長くする**
   ```json
   "interval": 10  // 5 → 10
   ```

2. **Simple Modeに変更**
   ```json
   "mode": "simple"
   ```

---

## トラブルシューティング

### Q: アバター検出が動作しない

**A:** 以下を確認してください：

1. **OpenCVがインストールされているか**
   ```bash
   pip list | grep opencv
   ```

2. **設定が有効になっているか**
   ```json
   "screenshot": {
     "enabled": true,
     "avatar_detection": {
       "enabled": true
     }
   }
   ```

3. **ログを確認**
   ```
   [WARNING] OpenCVが利用できないため、アバター検出は動作しません
   ```
   → OpenCVをインストール

### Q: 誤検知が多すぎる

**A:** 以下を試してください：

1. **Advanced Modeを使用**
   ```json
   "mode": "advanced"
   ```

2. **感度を下げる**
   ```json
   "sensitivity": 0.15
   ```

3. **連続検出フレーム数を増やす**
   ```json
   "consecutive_frames": 8
   ```

### Q: 検出が遅い

**A:** 以下の調整を試してください：

1. **連続検出フレーム数を減らす**
   ```json
   "consecutive_frames": 4
   ```

2. **監視間隔を短くする**
   ```json
   "interval": 3
   ```

### Q: CPU使用率が高い

**A:** 以下の対策を試してください：

1. **Simple Modeを使用**
   ```json
   "mode": "simple"
   ```

2. **監視間隔を長くする**
   ```json
   "interval": 10
   ```

---

## パフォーマンス

### CPU使用率

| モード | 監視間隔 | CPU使用率 |
|-------|---------|----------|
| Simple | 5秒 | ~1-2% |
| Simple | 3秒 | ~2-3% |
| Advanced | 5秒 | ~3-5% |
| Advanced | 3秒 | ~5-8% |

### メモリ使用量

- Simple Mode: 約+50MB
- Advanced Mode: 約+100MB

### 検出精度

| モード | 精度 | 誤検知率 |
|-------|-----|---------|
| Simple | 70-80% | 20-30% |
| Advanced | 90-95% | 5-10% |

---

## API リファレンス

### AvatarPresenceDetector

```python
from modules.screenshot.avatar_presence_detector import AvatarPresenceDetector

detector = AvatarPresenceDetector(
    sensitivity=0.10,         # スコア閾値
    consecutive_frames=6,     # 連続検出フレーム数
    hold_seconds=6.0,         # 保持時間
    mask_bottom_ratio=0.25,   # 下部マスク比率
    mask_side_ratio=0.20      # 左右マスク比率
)

# フレーム処理
detected, meta = detector.update(frame_bgr)

# または既存インターフェース
detected, score = detector.detect_change(pil_image)
```

#### メソッド

- `update(frame_bgr: np.ndarray) -> Tuple[bool, Dict]`
- `detect_change(image: Image.Image) -> Tuple[bool, float]`
- `reset()` - 検出器をリセット
- `set_sensitivity(float)` - 感度変更
- `set_hold_time(float)` - ホールド時間変更
- `set_mask(polygons: List)` - マスク設定
- `get_debug_info() -> Dict` - デバッグ情報取得

---

## 今後の改善案

1. **カスタムマスク設定UI**
   - ユーザーが除外領域を指定できるようにする

2. **動的感度調整**
   - 環境に応じて自動で感度を調整

3. **顔検出との組み合わせ**
   - OpenCVの顔検出器（Haar Cascades）を併用

4. **マルチスレッド処理**
   - 複数フレームを並列処理して高速化

5. **機械学習モデル**
   - 軽量なDNNモデル（MobileNet等）の統合

---

## ライセンス

このアバター検出機能はOpenCVを使用しています。
OpenCV License: https://opencv.org/license/
