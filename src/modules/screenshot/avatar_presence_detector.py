#!/usr/bin/env python3
"""
高精度アバター出現検出モジュール（3ゲート方式・AI不使用）
MOG2背景差分 + Optical Flow + Haar Cascade + ミラー抑止 + 時系列判定
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
    高精度アバター出現検出クラス（3ゲート方式）

    ゲート1: Optical Flow（動き検出）
    ゲート2: Haar Cascade（上半身・顔検出）
    ゲート3: ミラー抑止（自動マスク + テンプレート一致）
    """

    def __init__(
        self,
        sensitivity: float = 0.10,
        consecutive_frames: int = 6,
        hold_seconds: float = 6.0,
        mask_bottom_ratio: float = 0.25,
        mask_side_ratio: float = 0.20,
        flow_min: float = 0.35,
        base_score_threshold: float = 0.45,
        warmup_frames: int = 30
    ):
        """
        初期化（3ゲート方式）

        Args:
            sensitivity: 最終スコアの閾値（0.0～1.0、デフォルト: 0.10）
            consecutive_frames: 連続検出フレーム数（デフォルト: 6）
            hold_seconds: 検出後の保持時間（秒、デフォルト: 6.0）
            mask_bottom_ratio: 画面下部のマスク比率（デフォルト: 0.25）
            mask_side_ratio: 画面左右のマスク比率（デフォルト: 0.20）
            flow_min: Optical Flowの最小閾値（デフォルト: 0.35）
            base_score_threshold: ベーススコアの閾値（デフォルト: 0.45）
            warmup_frames: ミラー検出のウォームアップ期間（デフォルト: 30）
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
        self.flow_min = flow_min
        self.base_score_threshold = base_score_threshold
        self.warmup_frames = warmup_frames

        # MOG2背景差分器
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=300,
            varThreshold=16,
            detectShadows=True
        )

        # マスク（HUD/UI/ミラー領域除外）
        self.mask: Optional[np.ndarray] = None
        self.frame_shape: Optional[Tuple[int, int]] = None

        # Optical Flow用
        self.prev_gray: Optional[np.ndarray] = None
        self.flow_hist = deque(maxlen=5)  # ブロブ内フロー量の履歴（M=5フレーム）

        # ミラー抑止用
        self.mirror_boxes: List[Tuple[int, int, int, int]] = []  # [(x,y,w,h),...]
        self.frame_counter: int = 0

        # Haar Cascade（上半身・顔検出）
        self.cascade_face = None
        self.cascade_upper = None
        try:
            haar_path = cv2.data.haarcascades
            self.cascade_face = cv2.CascadeClassifier(
                haar_path + "haarcascade_frontalface_default.xml"
            )
            self.cascade_upper = cv2.CascadeClassifier(
                haar_path + "haarcascade_upperbody.xml"
            )
            if self.cascade_face.empty() or self.cascade_upper.empty():
                logger.warning("Haar Cascade分類器のロードに失敗しました")
                self.cascade_face = None
                self.cascade_upper = None
            else:
                logger.info("Haar Cascade分類器をロードしました")
        except Exception as e:
            logger.warning(f"Haar Cascadeのロード中にエラー: {e}")
            self.cascade_face = None
            self.cascade_upper = None

        # 時系列判定用
        self.score_queue = deque(maxlen=consecutive_frames)
        self.detected = False
        self.last_detection_time: float = 0
        self.hold_until: float = 0

        # 検出時のフレームをキャッシュ
        self.last_detected_frame: Optional[np.ndarray] = None
        self.last_detected_frame_pil: Optional[Image.Image] = None

        # デバッグ情報
        self.last_meta: Dict = {}

        logger.info(f"AvatarPresenceDetector initialized (3-Gate Mode)")
        logger.info(f"  - sensitivity={sensitivity}, frames={consecutive_frames}, hold={hold_seconds}s")
        logger.info(f"  - flow_min={flow_min}, base_threshold={base_score_threshold}, warmup={warmup_frames}")

    def _create_default_mask(self, height: int, width: int) -> np.ndarray:
        """
        デフォルトマスクを生成（HUD/チャット/UI領域を除外）

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

        logger.info(f"デフォルトマスク作成: {width}x{height}, "
                   f"有効領域: X={left_x}~{right_x}, Y={top_y}~{bottom_y}")

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

    def _detect_mirror_boxes(self, frame_gray: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        Canny→輪郭→approxPolyDPで大矩形フレーム（ミラー）を抽出

        Args:
            frame_gray: グレースケールフレーム

        Returns:
            List[Tuple[int, int, int, int]]: 検出された矩形リスト [(x,y,w,h),...]
        """
        try:
            # Cannyエッジ検出
            edges = cv2.Canny(frame_gray, 50, 150)

            # 輪郭抽出
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            mirror_boxes = []
            total_pixels = frame_gray.shape[0] * frame_gray.shape[1]

            for contour in contours:
                # 多角形近似
                epsilon = 0.02 * cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, epsilon, True)

                # 4角形のみ
                if len(approx) != 4:
                    continue

                x, y, w, h = cv2.boundingRect(approx)
                area = w * h
                area_ratio = area / total_pixels

                # 面積比10%～60%
                if area_ratio < 0.10 or area_ratio > 0.60:
                    continue

                # 長辺/短辺 > 1.2
                aspect = max(w, h) / (min(w, h) + 1e-6)
                if aspect < 1.2:
                    continue

                # 外枠の太さチェック（二重エッジ傾向）
                # 矩形周辺の3～8px幅でエッジ密度が高いか確認
                border_mask = np.zeros_like(edges)
                cv2.rectangle(border_mask, (x, y), (x + w, y + h), 255, 5)  # 5px枠
                border_edges = cv2.bitwise_and(edges, border_mask)
                border_density = np.count_nonzero(border_edges) / (border_mask.size + 1e-6)

                if border_density > 0.05:  # 枠のエッジ密度が5%以上
                    mirror_boxes.append((x, y, w, h))
                    logger.info(f"ミラー候補検出: 位置=({x},{y}), サイズ={w}x{h}, "
                               f"面積比={area_ratio*100:.1f}%, エッジ密度={border_density*100:.1f}%")

            return mirror_boxes

        except Exception as e:
            logger.debug(f"ミラー検出エラー: {e}")
            return []

    def _iou_with_any(self, box: Tuple[int, int, int, int],
                     boxes: List[Tuple[int, int, int, int]],
                     thresh: float = 0.3) -> float:
        """
        box と boxes の最大IoUを返す

        Args:
            box: 対象矩形 (x, y, w, h)
            boxes: 比較矩形リスト [(x,y,w,h),...]
            thresh: IoU閾値（デフォルト: 0.3）

        Returns:
            float: 最大IoU値
        """
        if not boxes:
            return 0.0

        x1, y1, w1, h1 = box
        max_iou = 0.0

        for x2, y2, w2, h2 in boxes:
            # 交差領域
            ix = max(x1, x2)
            iy = max(y1, y2)
            iw = min(x1 + w1, x2 + w2) - ix
            ih = min(y1 + h1, y2 + h2) - iy

            if iw <= 0 or ih <= 0:
                continue

            intersection = iw * ih
            union = w1 * h1 + w2 * h2 - intersection
            iou = intersection / (union + 1e-6)

            max_iou = max(max_iou, iou)

        return max_iou

    def _blob_flow_ok(self, prev_gray: np.ndarray, curr_gray: np.ndarray,
                     bbox: Tuple[int, int, int, int],
                     flow_min: float = 0.35) -> Tuple[bool, float]:
        """
        Farnebackのdense optical flowでブロブ内の平均|v|を算出

        Args:
            prev_gray: 前フレーム（グレースケール）
            curr_gray: 現フレーム（グレースケール）
            bbox: ブロブの矩形 (x, y, w, h)
            flow_min: 最小フロー閾値（デフォルト: 0.35）

        Returns:
            Tuple[bool, float]: (閾値を超えているか, フロー平均値)
        """
        try:
            x, y, w, h = bbox

            # ROI抽出
            prev_roi = prev_gray[y:y+h, x:x+w]
            curr_roi = curr_gray[y:y+h, x:x+w]

            if prev_roi.size == 0 or curr_roi.size == 0:
                return False, 0.0

            # Optical Flow計算（Farneback法）
            flow = cv2.calcOpticalFlowFarneback(
                prev_roi, curr_roi,
                None,
                pyr_scale=0.5,
                levels=3,
                winsize=15,
                iterations=3,
                poly_n=5,
                poly_sigma=1.2,
                flags=0
            )

            # フロー量の平均
            mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            mean_mag = np.mean(mag)

            # 履歴に追加（5フレーム移動平均）
            self.flow_hist.append(mean_mag)
            flow_avg = np.mean(self.flow_hist) if len(self.flow_hist) > 0 else 0.0

            # 正規化（画像サイズによらず0～1程度に）
            # 画像の対角線長さで正規化
            diag = np.sqrt(w**2 + h**2)
            flow_normalized = flow_avg / (diag + 1e-6)

            is_ok = flow_normalized >= flow_min

            if is_ok:
                logger.info(f"Optical Flow OK: {flow_normalized:.3f} >= {flow_min} "
                           f"(raw={flow_avg:.2f}, hist={len(self.flow_hist)})")

            return is_ok, flow_normalized

        except Exception as e:
            logger.debug(f"Optical Flow計算エラー: {e}")
            return False, 0.0

    def _upper_or_face_hit(self, gray: np.ndarray,
                          bbox_upper: Tuple[int, int, int, int]) -> bool:
        """
        上半身/顔カスケードのどちらかが1件でもヒットすれば True

        Args:
            gray: グレースケールフレーム全体
            bbox_upper: ブロブの上2/3領域 (x, y, w, h)

        Returns:
            bool: カスケードがヒットしたか
        """
        if self.cascade_face is None and self.cascade_upper is None:
            return False

        try:
            x, y, w, h = bbox_upper

            # ROI抽出
            roi = gray[y:y+h, x:x+w]

            if roi.size == 0:
                return False

            # 顔検出
            if self.cascade_face is not None:
                faces = self.cascade_face.detectMultiScale(
                    roi,
                    scaleFactor=1.1,
                    minNeighbors=3,
                    minSize=(20, 20)
                )
                if len(faces) > 0:
                    logger.info(f"顔検出ヒット: {len(faces)}個")
                    return True

            # 上半身検出
            if self.cascade_upper is not None:
                uppers = self.cascade_upper.detectMultiScale(
                    roi,
                    scaleFactor=1.1,
                    minNeighbors=3,
                    minSize=(30, 30)
                )
                if len(uppers) > 0:
                    logger.info(f"上半身検出ヒット: {len(uppers)}個")
                    return True

            return False

        except Exception as e:
            logger.debug(f"Cascade検出エラー: {e}")
            return False

    def _mask_mirror_labels(self, frame_gray: np.ndarray):
        """
        "HQ Mirror""LQ Mirror"風のボタン矩形をテンプレート一致で検出してマスク

        Args:
            frame_gray: グレースケールフレーム
        """
        if self.mask is None:
            return

        try:
            # 簡易テンプレート生成（白地+内枠）
            # "HQ Mirror"ボタンっぽい形状：幅80～120px、高さ25～35px
            templates = []
            for w in [80, 100, 120]:
                for h in [25, 30, 35]:
                    templ = np.ones((h, w), dtype=np.uint8) * 255
                    cv2.rectangle(templ, (2, 2), (w-3, h-3), 128, 1)
                    templates.append(templ)

            # テンプレートマッチング
            for templ in templates:
                result = cv2.matchTemplate(frame_gray, templ, cv2.TM_CCOEFF_NORMED)
                threshold = 0.70
                loc = np.where(result >= threshold)

                for pt in zip(*loc[::-1]):  # (x, y)
                    x, y = pt
                    h, w = templ.shape
                    # マスク領域を拡大して塗りつぶし
                    x1 = max(0, x - 10)
                    y1 = max(0, y - 10)
                    x2 = min(self.mask.shape[1], x + w + 10)
                    y2 = min(self.mask.shape[0], y + h + 10)
                    self.mask[y1:y2, x1:x2] = 0
                    logger.info(f"ミラーラベル検出: 位置=({x},{y}), サイズ={w}x{h}")

        except Exception as e:
            logger.debug(f"ミラーラベル検出エラー: {e}")

    def _calculate_blob_score(
        self,
        blob_mask: np.ndarray,
        stats: np.ndarray,
        label: int,
        frame_gray: np.ndarray
    ) -> float:
        """
        ブロブのベーススコアを計算（面積・縦横比・頭肩・エッジ）

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
            logger.debug(f"面積比が範囲外: {area_ratio*100:.3f}%")
            return 0.0

        score = 0.0

        # 2. 面積スコア（0～0.3）
        if 0.01 <= area_ratio <= 0.15:
            area_score = 0.3
        elif 0.005 <= area_ratio < 0.01:
            area_score = 0.15
        else:
            area_score = 0.1
        score += area_score

        # 3. アスペクト比（縦長）スコア（0～0.25）
        aspect_ratio = h / w
        if aspect_ratio > 1.1:
            if 1.5 <= aspect_ratio <= 2.5:
                aspect_score = 0.25
            elif 1.1 <= aspect_ratio < 1.5:
                aspect_score = 0.15
            else:
                aspect_score = 0.1
        else:
            aspect_score = 0.0
        score += aspect_score

        # 4. 頭肩パターン（0～0.25）
        try:
            region_mask = (blob_mask == label).astype(np.uint8)
            third_h = h // 3

            top_region = region_mask[y:y+third_h, x:x+w]
            top_width = np.sum(top_region, axis=1).max() if top_region.size > 0 else 0

            mid_region = region_mask[y+third_h:y+2*third_h, x:x+w]
            mid_width = np.sum(mid_region, axis=1).max() if mid_region.size > 0 else 0

            if mid_width > top_width * 1.1:
                head_shoulder_score = 0.25
            elif mid_width > top_width:
                head_shoulder_score = 0.15
            else:
                head_shoulder_score = 0.0
        except Exception:
            head_shoulder_score = 0.0
        score += head_shoulder_score

        # 5. エッジ密度スコア（0～0.20）
        try:
            roi = frame_gray[y:y+h, x:x+w]
            if roi.size > 0:
                edges = cv2.Canny(roi, 50, 150)
                edge_density = np.count_nonzero(edges) / edges.size
                if 0.05 <= edge_density <= 0.30:
                    edge_score = 0.20
                elif 0.02 <= edge_density < 0.05:
                    edge_score = 0.10
                else:
                    edge_score = 0.05
            else:
                edge_score = 0.0
        except Exception:
            edge_score = 0.0
        score += edge_score

        logger.info(f"ベーススコア: {score:.3f} (面積={area_score:.2f}, "
                   f"縦横比={aspect_score:.2f}, 頭肩={head_shoulder_score:.2f}, "
                   f"エッジ={edge_score:.2f})")

        return score

    def update(self, frame_bgr: np.ndarray) -> Tuple[bool, Dict]:
        """
        1フレーム処理してアバター出現を判定（3ゲート方式）

        Args:
            frame_bgr: BGRフォーマットのフレーム（OpenCV形式）

        Returns:
            Tuple[bool, Dict]: (detected, meta)
        """
        if not self.available:
            return False, {'error': 'OpenCV not available'}

        current_time = time.time()
        self.frame_counter += 1

        # フレーム形状を記録（サイズ変更を検出）
        current_shape = (frame_bgr.shape[0], frame_bgr.shape[1])
        if self.frame_shape is None or self.frame_shape != current_shape:
            logger.info(f"フレームサイズ変更を検出: {self.frame_shape} -> {current_shape}")
            self.frame_shape = current_shape
            self.mask = self._create_default_mask(*self.frame_shape)
            # サイズ変更時は背景モデルもリセット
            self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
                history=500,
                varThreshold=16,
                detectShadows=False
            )
            self.mirror_boxes = []  # ミラー情報もリセット
            self.frame_counter = 0  # ウォームアップを再開

        # グレースケール化
        frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        # ウォームアップ期間中：ミラー検出
        if self.frame_counter <= self.warmup_frames:
            detected_mirrors = self._detect_mirror_boxes(frame_gray)
            for mirror_box in detected_mirrors:
                # 重複チェック（IoU > 0.5でマージ）
                if self._iou_with_any(mirror_box, self.mirror_boxes, thresh=0.5) < 0.5:
                    self.mirror_boxes.append(mirror_box)
                    # マスクに反映
                    x, y, w, h = mirror_box
                    self.mask[y:y+h, x:x+w] = 0
                    logger.info(f"ミラーをマスクに追加: ({x},{y}) {w}x{h}")

        # ミラーラベル抑止
        self._mask_mirror_labels(frame_gray)

        # MOG2背景差分
        fg_mask = self.bg_subtractor.apply(frame_bgr, learningRate=0.001)
        fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)[1]

        # マスク適用（サイズ一致を確認）
        if self.mask is not None:
            if fg_mask.shape == self.mask.shape:
                fg_mask = cv2.bitwise_and(fg_mask, self.mask)
            else:
                logger.warning(f"マスクサイズ不一致: fg_mask={fg_mask.shape}, mask={self.mask.shape} - マスクを再生成します")
                self.mask = self._create_default_mask(fg_mask.shape[0], fg_mask.shape[1])
                fg_mask = cv2.bitwise_and(fg_mask, self.mask)

        # モルフォロジー処理
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)

        # ブロブ解析
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            fg_mask, connectivity=8
        )

        logger.info(f"検出されたブロブ数: {num_labels - 1}個")

        # 各ブロブを3ゲートで評価
        best_score = 0.0
        best_blob_info = {}

        for label in range(1, num_labels):
            x, y, w, h, area = stats[label]

            # ゲート3: ミラー抑止（IoU判定）
            if self._iou_with_any((x, y, w, h), self.mirror_boxes, thresh=0.3) > 0.3:
                logger.info(f"ブロブ#{label}: ミラー領域と重複のためスキップ")
                continue

            # ベーススコア計算
            base_score = self._calculate_blob_score(labels, stats, label, frame_gray)

            # ベーススコアが閾値未満ならスキップ
            if base_score < self.base_score_threshold:
                logger.debug(f"ブロブ#{label}: ベーススコア不足 ({base_score:.3f} < {self.base_score_threshold})")
                continue

            # ゲート1: Optical Flow
            flow_ok = False
            flow_mag = 0.0
            if self.prev_gray is not None:
                flow_ok, flow_mag = self._blob_flow_ok(
                    self.prev_gray, frame_gray, (x, y, w, h), self.flow_min
                )

            # ゲート2: Haar Cascade（上2/3領域）
            upper_h = int(2 * h / 3)
            cascade_ok = self._upper_or_face_hit(frame_gray, (x, y, w, upper_h))

            # 統合判定：
            # 1. 高スコア時はゲートバイパス（base_score >= 0.70）
            # 2. 通常判定：base_score >= threshold かつ (flow_ok or cascade_ok)
            bypass_gates = base_score >= 0.70
            normal_pass = base_score >= self.base_score_threshold and (flow_ok or cascade_ok)

            if bypass_gates or normal_pass:
                final_score = base_score
                if final_score > best_score:
                    best_score = final_score
                    best_blob_info = {
                        'label': label,
                        'bbox': (x, y, w, h),
                        'area': area,
                        'centroid': (int(centroids[label][0]), int(centroids[label][1])),
                        'score': final_score,
                        'base_score': base_score,
                        'flow_ok': flow_ok,
                        'flow_mag': flow_mag,
                        'cascade_ok': cascade_ok,
                        'bypass': bypass_gates
                    }
                    if bypass_gates:
                        logger.info(f"ブロブ#{label}: 高スコアバイパス！ score={final_score:.3f}")
                    else:
                        logger.info(f"ブロブ#{label}: 3ゲート通過！ score={final_score:.3f}, "
                                   f"flow={'OK' if flow_ok else 'NG'}({flow_mag:.3f}), "
                                   f"cascade={'OK' if cascade_ok else 'NG'}")
            else:
                logger.info(f"ブロブ#{label}: ゲート不通過 (score={base_score:.3f}, "
                           f"flow={'OK' if flow_ok else 'NG'}, cascade={'OK' if cascade_ok else 'NG'})")

        # 前フレーム更新
        self.prev_gray = frame_gray.copy()

        # スコアをキューに追加
        self.score_queue.append(best_score)

        # 時系列判定
        consecutive_detections = sum(1 for s in self.score_queue if s >= self.sensitivity)

        logger.info(f"Detection queue: best={best_score:.3f}, consecutive={consecutive_detections}/{self.consecutive_frames}, "
                   f"queue={[f'{s:.2f}' for s in self.score_queue]}")

        # ホールド状態チェック
        holding = current_time < self.hold_until

        # 検出判定
        newly_detected = False  # 初回検出フラグ
        if consecutive_detections >= self.consecutive_frames:
            if not self.detected:
                logger.info(f"アバター出現検出！ (score={best_score:.3f}, consecutive={consecutive_detections})")
                self.detected = True
                self.last_detection_time = current_time
                newly_detected = True  # 初回検出
                # 検出時のフレームをキャッシュ
                self.last_detected_frame = frame_bgr.copy()
                # PIL Image形式にも変換
                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                self.last_detected_frame_pil = Image.fromarray(frame_rgb)
            self.hold_until = current_time + self.hold_seconds
        elif holding:
            pass
        else:
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
            'threshold': self.sensitivity,
            'frame_counter': self.frame_counter,
            'mirror_boxes_count': len(self.mirror_boxes),
            'newly_detected': newly_detected  # 初回検出フラグを追加
        }

        self.last_meta = meta

        return self.detected, meta

    def detect_change(self, image: Image.Image) -> Tuple[bool, float]:
        """
        既存のAvatarDetectorと互換性のあるインターフェース

        Args:
            image: PIL Image オブジェクト

        Returns:
            Tuple[bool, float]: (検出されたか, 最高スコア)
        """
        if not self.available:
            return False, 0.0

        frame = np.array(image)

        if len(frame.shape) == 3:
            if frame.shape[2] == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            elif frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)

        detected, meta = self.update(frame)

        return detected, meta.get('best_score', 0.0)

    def reset(self):
        """検出器をリセット"""
        if not self.available:
            return

        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=300,
            varThreshold=16,
            detectShadows=True
        )

        self.score_queue.clear()
        self.flow_hist.clear()
        self.detected = False
        self.hold_until = 0
        self.prev_gray = None
        self.frame_counter = 0
        self.mirror_boxes.clear()
        self.last_detected_frame = None
        self.last_detected_frame_pil = None

        logger.info("AvatarPresenceDetector reset")

    def set_sensitivity(self, sensitivity: float):
        """感度を変更"""
        old_sensitivity = self.sensitivity
        self.sensitivity = max(0.0, min(1.0, sensitivity))
        logger.info(f"Sensitivity changed: {old_sensitivity} -> {self.sensitivity}")

    def set_hold_time(self, seconds: float):
        """ホールド時間を変更"""
        old_hold = self.hold_seconds
        self.hold_seconds = max(0.0, seconds)
        logger.info(f"Hold time changed: {old_hold}s -> {self.hold_seconds}s")

    @property
    def is_available(self) -> bool:
        """OpenCVが利用可能かどうか"""
        return self.available

    def get_debug_info(self) -> Dict:
        """デバッグ情報を取得"""
        return self.last_meta.copy()

    def get_detected_frame(self) -> Optional[Image.Image]:
        """
        最後に検出したフレームを取得（PIL Image形式）

        Returns:
            Optional[Image.Image]: 検出時のフレーム（未検出の場合はNone）
        """
        return self.last_detected_frame_pil
