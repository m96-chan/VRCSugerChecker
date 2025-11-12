#!/usr/bin/env python3
"""
アバター検出モジュール（AI不使用）
画像処理によるフレーム差分検出で他のアバターの出現を検知
"""

import logging
import numpy as np
from PIL import Image
from typing import Optional, Tuple
import time

logger = logging.getLogger(__name__)

# OpenCVのインポート（オプショナル）
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("OpenCV (cv2) が利用できません。アバター検出機能が制限されます")


class AvatarDetector:
    """
    画像処理ベースのアバター検出クラス
    フレーム差分により画面の大きな変化を検出
    """

    def __init__(self, sensitivity: float = 0.10, min_change_pixels: int = 10000):
        """
        初期化
        Args:
            sensitivity: 変化率の閾値（0.0～1.0、デフォルト: 0.10 = 10%）
            min_change_pixels: 最小変化ピクセル数（小さな変化を無視）
        """
        self.last_frame: Optional[np.ndarray] = None
        self.sensitivity = sensitivity
        self.min_change_pixels = min_change_pixels
        self.last_detection_time: float = 0
        self.detection_cooldown: float = 10.0  # 検出後10秒はクールダウン

        if not CV2_AVAILABLE:
            logger.warning("OpenCVが利用できないため、アバター検出は動作しません")
        else:
            logger.info(f"AvatarDetector initialized (sensitivity={sensitivity}, "
                       f"min_change={min_change_pixels}px)")

    def detect_change(self, image: Image.Image) -> Tuple[bool, float]:
        """
        フレーム差分で画面の変化を検出
        Args:
            image: PIL Image オブジェクト（スクリーンキャプチャ）
        Returns:
            Tuple[bool, float]: (変化が検出されたか, 変化率)
        """
        if not CV2_AVAILABLE:
            return False, 0.0

        # クールダウンチェック
        current_time = time.time()
        if current_time - self.last_detection_time < self.detection_cooldown:
            return False, 0.0

        try:
            # PIL ImageをNumPy配列に変換
            frame = np.array(image)

            # RGBからBGRに変換（OpenCV用）
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            elif len(frame.shape) == 3 and frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)

            # サイズを縮小して処理を高速化（640x360）
            height, width = frame.shape[:2]
            scale = min(640 / width, 360 / height)
            if scale < 1.0:
                new_width = int(width * scale)
                new_height = int(height * scale)
                frame = cv2.resize(frame, (new_width, new_height))

            # 初回は参照フレームとして保存
            if self.last_frame is None:
                self.last_frame = frame.copy()
                logger.debug("Reference frame initialized")
                return False, 0.0

            # フレーム差分を計算
            diff = cv2.absdiff(self.last_frame, frame)

            # グレースケール化
            gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)

            # ガウシアンブラーでノイズ除去
            blurred = cv2.GaussianBlur(gray_diff, (5, 5), 0)

            # 二値化（閾値30で変化を検出）
            _, thresh = cv2.threshold(blurred, 30, 255, cv2.THRESH_BINARY)

            # モルフォロジー変換でノイズをさらに除去
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

            # 変化ピクセル数をカウント
            changed_pixels = np.count_nonzero(thresh)
            total_pixels = thresh.size
            change_ratio = changed_pixels / total_pixels

            logger.debug(f"Change detection: {changed_pixels}/{total_pixels} pixels "
                        f"({change_ratio*100:.2f}%), threshold={self.sensitivity*100:.2f}%")

            # 変化が閾値を超えているかチェック
            is_changed = (change_ratio > self.sensitivity and
                         changed_pixels > self.min_change_pixels)

            if is_changed:
                logger.info(f"Large change detected! ratio={change_ratio*100:.2f}%, "
                           f"pixels={changed_pixels}")
                self.last_detection_time = current_time

            # 現在のフレームを次回の参照として保存
            self.last_frame = frame.copy()

            return is_changed, change_ratio

        except Exception as e:
            logger.error(f"Error in change detection: {e}")
            import traceback
            traceback.print_exc()
            return False, 0.0

    def reset(self):
        """
        参照フレームをリセット
        ワールド変更時などに呼び出す
        """
        self.last_frame = None
        self.last_detection_time = 0
        logger.info("AvatarDetector reset")

    def set_sensitivity(self, sensitivity: float):
        """
        感度を変更
        Args:
            sensitivity: 新しい感度（0.0～1.0）
        """
        old_sensitivity = self.sensitivity
        self.sensitivity = max(0.0, min(1.0, sensitivity))
        logger.info(f"Sensitivity changed: {old_sensitivity} -> {self.sensitivity}")

    def set_cooldown(self, seconds: float):
        """
        クールダウン時間を変更
        Args:
            seconds: クールダウン秒数
        """
        old_cooldown = self.detection_cooldown
        self.detection_cooldown = max(0.0, seconds)
        logger.info(f"Cooldown changed: {old_cooldown}s -> {self.detection_cooldown}s")

    @property
    def is_available(self) -> bool:
        """OpenCVが利用可能かどうか"""
        return CV2_AVAILABLE
