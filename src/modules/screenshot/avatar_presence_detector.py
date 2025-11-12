#!/usr/bin/env python3
"""
高精度アバター出現検出モジュール（AI不使用）
MOG2背景差分 + ブロブ解析 + 時系列判定による安定検出
"""

import logging
import numpy as np
from PIL import Image
from typing import Optional, Tuple, List, Dict
from collections import deque
import time

logger = logging.getLogger(__name__)

# OpenCVのインポート（オプショナル）
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("OpenCV (cv2) が利用できません。アバター検出機能が制限されます")


class AvatarPresenceDetector:
    """
    高精度アバター出現検出クラス
    MOG2背景差分 + ブロブ解析 + 時系列判定
    """

    def __init__(
        self,
        sensitivity: float = 0.10,
        consecutive_frames: int = 6,
        hold_seconds: float = 6.0,
        mask_bottom_ratio: float = 0.25,
        mask_side_ratio: float = 0.20
    ):
        """
        初期化
        Args:
            sensitivity: ブロブスコアの閾値（0.0～1.0、デフォルト: 0.10）
            consecutive_frames: 連続検出フレーム数（デフォルト: 6）
            hold_seconds: 検出後の保持時間（秒、デフォルト: 6.0）
            mask_bottom_ratio: 画面下部のマスク比率（0.0～1.0、デフォルト: 0.25）
            mask_side_ratio: 画面左右のマスク比率（0.0～1.0、デフォルト: 0.20）
        """
        if not CV2_AVAILABLE:
            logger.warning("OpenCVが利用できないため、アバター検出は動作しません")
            self.available = False
            return

        self.available = True
        self.sensitivity = sensitivity
        self.consecutive_frames = consecutive_frames
        self.hold_seconds = hold_seconds
        self.mask_bottom_ratio = mask_bottom_ratio
        self.mask_side_ratio = mask_side_ratio

        # MOG2背景差分器
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=300,
            varThreshold=16,
            detectShadows=True
        )

        # マスク（HUD/UI領域除外）
        self.mask: Optional[np.ndarray] = None
        self.frame_shape: Optional[Tuple[int, int]] = None

        # 時系列判定用
        self.score_queue = deque(maxlen=consecutive_frames)
        self.detected = False
        self.last_detection_time: float = 0
        self.hold_until: float = 0

        # デバッグ情報
        self.last_meta: Dict = {}

        logger.info(f"AvatarPresenceDetector initialized (sensitivity={sensitivity}, "
                   f"frames={consecutive_frames}, hold={hold_seconds}s)")

    def _create_default_mask(self, height: int, width: int) -> np.ndarray:
        """
        デフォルトマスクを生成（HUD/チャット/ミラー領域を除外）
        Args:
            height: フレーム高さ
            width: フレーム幅
        Returns:
            np.ndarray: マスク画像（255=有効、0=無効）
        """
        mask = np.ones((height, width), dtype=np.uint8) * 255

        # 画面下部を除外（チャット、通知など）
        bottom_y = int(height * (1 - self.mask_bottom_ratio))
        mask[bottom_y:, :] = 0

        # 画面左右を除外（UI、サイドメニューなど）
        left_x = int(width * self.mask_side_ratio)
        right_x = int(width * (1 - self.mask_side_ratio))
        mask[:, :left_x] = 0
        mask[:, right_x:] = 0

        # 画面上部を少し除外（タイトルバー、FPSカウンターなど）
        top_y = int(height * 0.05)
        mask[:top_y, :] = 0

        logger.debug(f"Default mask created: {width}x{height}, "
                    f"active area: {left_x}~{right_x}, {top_y}~{bottom_y}")

        return mask

    def set_mask(self, polygons: Optional[List[List[Tuple[int, int]]]] = None):
        """
        カスタムマスクを設定
        Args:
            polygons: マスク領域のポリゴンリスト（None=デフォルトマスク）
        """
        if not self.available or self.frame_shape is None:
            return

        height, width = self.frame_shape

        if polygons is None:
            self.mask = self._create_default_mask(height, width)
        else:
            mask = np.zeros((height, width), dtype=np.uint8)
            for polygon in polygons:
                pts = np.array(polygon, dtype=np.int32)
                cv2.fillPoly(mask, [pts], 255)
            self.mask = mask

        logger.info(f"Mask updated: {np.count_nonzero(self.mask)} active pixels")

    def _calculate_blob_score(
        self,
        blob_mask: np.ndarray,
        stats: np.ndarray,
        label: int,
        frame_gray: np.ndarray
    ) -> float:
        """
        ブロブのスコアを計算
        Args:
            blob_mask: ブロブマスク
            stats: cv2.connectedComponentsWithStats の結果
            label: ブロブラベル
            frame_gray: グレースケールフレーム
        Returns:
            float: スコア（0.0～1.0）
        """
        x, y, w, h, area = stats[label]

        if w == 0 or h == 0:
            return 0.0

        total_pixels = blob_mask.shape[0] * blob_mask.shape[1]
        area_ratio = area / total_pixels

        # 1. 面積比チェック（0.5%～25%）
        if area_ratio < 0.005 or area_ratio > 0.25:
            return 0.0

        score = 0.0

        # 2. 面積スコア（0～0.3）
        if 0.01 <= area_ratio <= 0.15:  # 理想的な範囲
            area_score = 0.3
        elif 0.005 <= area_ratio < 0.01:  # 小さめ
            area_score = 0.15
        else:  # 大きめ
            area_score = 0.1
        score += area_score

        # 3. アスペクト比（縦長）スコア（0～0.25）
        aspect_ratio = h / w
        if aspect_ratio > 1.1:  # 縦長（人型）
            if 1.5 <= aspect_ratio <= 2.5:  # 理想的
                aspect_score = 0.25
            elif 1.1 <= aspect_ratio < 1.5:  # やや縦長
                aspect_score = 0.15
            else:  # 非常に縦長
                aspect_score = 0.1
        else:
            aspect_score = 0.0
        score += aspect_score

        # 4. 頭肩パターン（上1/3より中1/3が広い）スコア（0～0.25）
        try:
            region_mask = (blob_mask == label).astype(np.uint8)
            y_end = y + h
            third_h = h // 3

            # 上1/3の水平投影
            top_region = region_mask[y:y+third_h, x:x+w]
            top_width = np.sum(top_region, axis=1).max() if top_region.size > 0 else 0

            # 中1/3の水平投影
            mid_region = region_mask[y+third_h:y+2*third_h, x:x+w]
            mid_width = np.sum(mid_region, axis=1).max() if mid_region.size > 0 else 0

            if mid_width > top_width * 1.1:  # 中央が上部より10%以上広い
                head_shoulder_score = 0.25
            elif mid_width > top_width:
                head_shoulder_score = 0.15
            else:
                head_shoulder_score = 0.0
        except Exception as e:
            logger.debug(f"Head-shoulder pattern check failed: {e}")
            head_shoulder_score = 0.0
        score += head_shoulder_score

        # 5. エッジ密度スコア（0～0.20）
        try:
            roi = frame_gray[y:y_end, x:x+w]
            if roi.size > 0:
                edges = cv2.Canny(roi, 50, 150)
                edge_density = np.count_nonzero(edges) / edges.size
                if 0.05 <= edge_density <= 0.30:  # 適度なエッジ密度
                    edge_score = 0.20
                elif 0.02 <= edge_density < 0.05:
                    edge_score = 0.10
                else:
                    edge_score = 0.05
            else:
                edge_score = 0.0
        except Exception as e:
            logger.debug(f"Edge density check failed: {e}")
            edge_score = 0.0
        score += edge_score

        logger.debug(f"Blob score: {score:.3f} (area={area_score:.2f}, "
                    f"aspect={aspect_score:.2f}, head_shoulder={head_shoulder_score:.2f}, "
                    f"edge={edge_score:.2f})")

        return score

    def update(self, frame_bgr: np.ndarray) -> Tuple[bool, Dict]:
        """
        1フレーム処理してアバター出現を判定
        Args:
            frame_bgr: BGRフォーマットのフレーム（OpenCV形式）
        Returns:
            Tuple[bool, Dict]: (detected, meta)
                detected: アバターが検出されたか
                meta: {
                    'best_score': float,
                    'blob_count': int,
                    'blob_info': dict,
                    'queue_length': int,
                    'holding': bool,
                    'consecutive_detections': int
                }
        """
        if not self.available:
            return False, {'error': 'OpenCV not available'}

        current_time = time.time()

        # フレーム形状を記録
        if self.frame_shape is None:
            self.frame_shape = (frame_bgr.shape[0], frame_bgr.shape[1])
            self.mask = self._create_default_mask(*self.frame_shape)

        # グレースケール化（エッジ検出用）
        frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        # MOG2背景差分（学習率を小さく）
        fg_mask = self.bg_subtractor.apply(frame_bgr, learningRate=0.001)

        # 影を除去（127=影、255=前景）
        fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)[1]

        # マスク適用
        if self.mask is not None:
            fg_mask = cv2.bitwise_and(fg_mask, self.mask)

        # モルフォロジー処理（ノイズ除去）
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)

        # ブロブ解析
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            fg_mask, connectivity=8
        )

        # 各ブロブをスコアリング
        best_score = 0.0
        best_blob_info = {}
        blob_scores = []

        for label in range(1, num_labels):  # 0はバックグラウンド
            score = self._calculate_blob_score(labels, stats, label, frame_gray)
            blob_scores.append(score)

            if score > best_score:
                best_score = score
                x, y, w, h, area = stats[label]
                best_blob_info = {
                    'label': label,
                    'bbox': (x, y, w, h),
                    'area': area,
                    'centroid': (int(centroids[label][0]), int(centroids[label][1])),
                    'score': score
                }

        # スコアをキューに追加
        self.score_queue.append(best_score)

        # 時系列判定
        consecutive_detections = sum(1 for s in self.score_queue if s >= self.sensitivity)

        # ホールド状態チェック
        holding = current_time < self.hold_until

        # 検出判定
        if consecutive_detections >= self.consecutive_frames:
            # 連続検出条件を満たした
            if not self.detected:
                logger.info(f"アバター出現検出！ (score={best_score:.3f}, "
                           f"consecutive={consecutive_detections})")
                self.detected = True
                self.last_detection_time = current_time

            # ホールド期間を延長
            self.hold_until = current_time + self.hold_seconds

        elif holding:
            # ホールド期間中は検出状態を維持
            pass
        else:
            # 検出終了
            if self.detected:
                logger.info("アバター検出終了")
            self.detected = False

        # メタ情報
        meta = {
            'best_score': best_score,
            'blob_count': num_labels - 1,
            'blob_info': best_blob_info,
            'queue_length': len(self.score_queue),
            'holding': holding,
            'consecutive_detections': consecutive_detections,
            'threshold': self.sensitivity
        }

        self.last_meta = meta

        return self.detected, meta

    def detect_change(self, image: Image.Image) -> Tuple[bool, float]:
        """
        既存のAvatarDetectorと互換性のあるインターフェース
        Args:
            image: PIL Image オブジェクト（スクリーンキャプチャ）
        Returns:
            Tuple[bool, float]: (変化が検出されたか, 最高スコア)
        """
        if not self.available:
            return False, 0.0

        # PIL ImageをBGR配列に変換
        frame = np.array(image)

        # RGBからBGRに変換（OpenCV用）
        if len(frame.shape) == 3:
            if frame.shape[2] == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            elif frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)

        # update()を呼び出し
        detected, meta = self.update(frame)

        return detected, meta.get('best_score', 0.0)

    def reset(self):
        """
        検出器をリセット（ワールド変更時など）
        """
        if not self.available:
            return

        # 背景モデルをリセット
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=300,
            varThreshold=16,
            detectShadows=True
        )

        # スコアキューをクリア
        self.score_queue.clear()

        # 検出状態をリセット
        self.detected = False
        self.hold_until = 0

        # マスクはリセットしない（同じ解像度を想定）

        logger.info("AvatarPresenceDetector reset")

    def set_sensitivity(self, sensitivity: float):
        """
        感度を変更
        Args:
            sensitivity: 新しい感度（0.0～1.0）
        """
        old_sensitivity = self.sensitivity
        self.sensitivity = max(0.0, min(1.0, sensitivity))
        logger.info(f"Sensitivity changed: {old_sensitivity} -> {self.sensitivity}")

    def set_hold_time(self, seconds: float):
        """
        ホールド時間を変更
        Args:
            seconds: ホールド秒数
        """
        old_hold = self.hold_seconds
        self.hold_seconds = max(0.0, seconds)
        logger.info(f"Hold time changed: {old_hold}s -> {self.hold_seconds}s")

    @property
    def is_available(self) -> bool:
        """OpenCVが利用可能かどうか"""
        return self.available

    def get_debug_info(self) -> Dict:
        """
        デバッグ情報を取得
        Returns:
            Dict: 最後のメタ情報
        """
        return self.last_meta.copy()
