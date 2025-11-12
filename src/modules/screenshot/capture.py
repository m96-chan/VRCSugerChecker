#!/usr/bin/env python3
"""
スクリーンショット撮影モジュール
VRChatウィンドウを自動キャプチャする機能

機能:
- VRChatウィンドウの検出とキャプチャ
- インスタンス変更時の自動撮影
- 定期的な自動撮影（3分おき）
- logsフォルダへの保存
"""
import logging
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Callable
import subprocess

# Win32 API imports
try:
    import win32gui
    import win32ui
    import win32con
    import win32api
    from ctypes import windll
    from PIL import Image
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    logging.warning("pywin32が利用できません。フォールバック方式でスクリーンショットを撮影します")

logger = logging.getLogger(__name__)

# アバター検出モジュールのインポート（オプショナル）
try:
    from .avatar_detector import AvatarDetector
    AVATAR_DETECTOR_AVAILABLE = True
except ImportError:
    AVATAR_DETECTOR_AVAILABLE = False
    logger.warning("AvatarDetector is not available")

# 高精度アバター検出モジュール（オプショナル）
try:
    from .avatar_presence_detector import AvatarPresenceDetector
    AVATAR_PRESENCE_DETECTOR_AVAILABLE = True
except ImportError:
    AVATAR_PRESENCE_DETECTOR_AVAILABLE = False
    logger.warning("AvatarPresenceDetector is not available")


class ScreenshotCapture:
    """スクリーンショット撮影クラス"""

    def __init__(self, logs_dir: Path, screenshot_callback: Optional[Callable[[Path, str], None]] = None):
        """
        初期化
        Args:
            logs_dir: ログディレクトリのパス（スクリーンショット保存先）
            screenshot_callback: スクリーンショット撮影時のコールバック関数 (screenshot_path, reason) -> None
        """
        self.logs_dir = logs_dir
        self.is_auto_capture_running = False
        self.auto_capture_thread: Optional[threading.Thread] = None
        self.auto_capture_interval = 180  # 3分 = 180秒
        self._stop_event = threading.Event()
        self.screenshot_callback = screenshot_callback

        # アバター検出機能
        self.avatar_detector: Optional['AvatarDetector'] = None
        self.is_avatar_detection_running = False
        self.avatar_detection_thread: Optional[threading.Thread] = None
        self.avatar_detection_interval = 5  # 5秒
        self._avatar_detection_stop_event = threading.Event()
        self.current_user_count = 0  # 現在のユーザー数（自分を除く）

        # スクリーンショット保存用のサブディレクトリを作成
        self.screenshots_dir = logs_dir / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    def find_vrchat_window(self) -> Optional[int]:
        """
        VRChatウィンドウを検索
        Returns:
            Optional[int]: VRChatウィンドウハンドル（見つからない場合はNone）
        """
        if WIN32_AVAILABLE:
            return self._find_vrchat_window_win32()
        else:
            return self._find_vrchat_window_powershell()

    def _find_vrchat_window_win32(self) -> Optional[int]:
        """
        Win32 APIを使用してVRChatウィンドウを検索
        Returns:
            Optional[int]: VRChatウィンドウハンドル（見つからない場合はNone）
        """
        try:
            vrchat_hwnd = None

            def enum_windows_callback(hwnd, _):
                nonlocal vrchat_hwnd
                if win32gui.IsWindowVisible(hwnd):
                    window_text = win32gui.GetWindowText(hwnd)
                    # VRChatウィンドウのタイトルを検索
                    if "VRChat" in window_text:
                        vrchat_hwnd = hwnd
                        return False  # 見つかったので列挙を停止
                return True

            win32gui.EnumWindows(enum_windows_callback, None)
            return vrchat_hwnd

        except Exception as e:
            logger.error(f"VRChatウィンドウの検索中にエラー (Win32): {e}")
            return None

    def _find_vrchat_window_powershell(self) -> Optional[int]:
        """
        PowerShellを使用してVRChatウィンドウを検索（フォールバック）
        Returns:
            Optional[int]: VRChatウィンドウハンドル（見つからない場合はNone）
        """
        try:
            # PowerShell経由でVRChatウィンドウを検索
            result = subprocess.run(
                ["powershell.exe", "-Command",
                 "Get-Process -Name VRChat -ErrorAction SilentlyContinue | Select-Object -First 1 MainWindowHandle"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=5
            )

            # ウィンドウハンドルが存在するかチェック
            output = result.stdout.strip()
            if output and "MainWindowHandle" in output:
                lines = output.split('\n')
                if len(lines) > 2:  # ヘッダー行をスキップ
                    handle_line = lines[2].strip()
                    if handle_line and handle_line != "0":
                        try:
                            return int(handle_line)
                        except ValueError:
                            pass

            return None
        except Exception as e:
            logger.error(f"VRChatウィンドウの検索中にエラー (PowerShell): {e}")
            return None

    def capture_vrchat_window(self, prefix: str = "vrchat", reason: str = "") -> Optional[Path]:
        """
        VRChatウィンドウをキャプチャ
        Args:
            prefix: ファイル名のプレフィックス
            reason: 撮影理由（ファイル名に含める）
        Returns:
            Path: 保存されたスクリーンショットのパス（失敗時はNone）
        """
        try:
            # VRChatウィンドウが存在するかチェック
            hwnd = self.find_vrchat_window()
            if not hwnd:
                logger.warning("VRChatウィンドウが見つかりません")
                return None

            # ファイル名を生成
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if reason:
                filename = f"{prefix}_{reason}_{timestamp}.png"
            else:
                filename = f"{prefix}_{timestamp}.png"

            screenshot_path = self.screenshots_dir / filename

            # Win32 APIを使用してキャプチャ
            if WIN32_AVAILABLE:
                success = self._capture_window_win32(hwnd, screenshot_path)
            else:
                success = self._capture_window_powershell(screenshot_path)

            if success and screenshot_path.exists():
                logger.info(f"スクリーンショットを保存: {filename}")
                return screenshot_path
            else:
                logger.error(f"スクリーンショットの保存に失敗")
                return None

        except Exception as e:
            logger.error(f"スクリーンショットのキャプチャ中にエラー: {e}")
            return None

    def _capture_window_win32(self, hwnd: int, save_path: Path) -> bool:
        """
        Win32 APIを使用してウィンドウをキャプチャ
        Args:
            hwnd: ウィンドウハンドル
            save_path: 保存先パス
        Returns:
            bool: 成功した場合True
        """
        try:
            # ウィンドウの位置とサイズを取得
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = right - left
            height = bottom - top

            # ウィンドウが最小化されている場合はスキップ
            if width <= 0 or height <= 0:
                logger.warning("ウィンドウが最小化されているか、サイズが0です")
                return False

            # デバイスコンテキストを取得
            hwndDC = win32gui.GetWindowDC(hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()

            # ビットマップを作成
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)

            # ウィンドウの内容をコピー
            # ctypes経由でPrintWindowを呼び出す
            # PW_RENDERFULLCONTENT = 0x00000002
            # PW_CLIENTONLY = 0x00000001
            PW_RENDERFULLCONTENT = 0x00000002
            result = windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), PW_RENDERFULLCONTENT)

            # 結果が0の場合、通常のBitBltを試す
            if result == 0:
                logger.warning("PrintWindowが失敗しました。BitBltを試します")
                result = saveDC.BitBlt(
                    (0, 0), (width, height),
                    mfcDC,
                    (0, 0),
                    win32con.SRCCOPY
                )

            # ビットマップをPIL Imageに変換
            bmpinfo = saveBitMap.GetInfo()
            bmpstr = saveBitMap.GetBitmapBits(True)

            img = Image.frombuffer(
                'RGB',
                (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                bmpstr, 'raw', 'BGRX', 0, 1
            )

            # ファイルに保存
            img.save(str(save_path), 'PNG')

            # クリーンアップ
            win32gui.DeleteObject(saveBitMap.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwndDC)

            return True

        except Exception as e:
            logger.error(f"Win32ウィンドウキャプチャ中にエラー: {e}")
            return False

    def _capture_window_powershell(self, save_path: Path) -> bool:
        """
        PowerShellを使用してウィンドウをキャプチャ（フォールバック）
        Args:
            save_path: 保存先パス
        Returns:
            bool: 成功した場合True
        """
        try:
            # PowerShellスクリプトでスクリーンショットを撮影
            ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# VRChatプロセスを取得
$process = Get-Process -Name "VRChat" -ErrorAction SilentlyContinue | Select-Object -First 1

if ($process -eq $null) {{
    Write-Host "VRChat process not found"
    exit 1
}}

# 画面全体をキャプチャ（VRChatがフルスクリーンの場合）
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)

# ファイルに保存
$bitmap.Save("{str(save_path).replace(chr(92), chr(92)*2)}", [System.Drawing.Imaging.ImageFormat]::Png)

# クリーンアップ
$graphics.Dispose()
$bitmap.Dispose()

Write-Host "Screenshot saved"
"""

            # PowerShellスクリプトを実行
            result = subprocess.run(
                ["powershell.exe", "-Command", ps_script],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=10
            )

            return result.returncode == 0

        except Exception as e:
            logger.error(f"PowerShellウィンドウキャプチャ中にエラー: {e}")
            return False

    def capture_on_instance_change(self, instance_id: str, world_name: str = "") -> Optional[Path]:
        """
        インスタンス変更時のスクリーンショットを撮影
        Args:
            instance_id: インスタンスID
            world_name: ワールド名
        Returns:
            Path: 保存されたスクリーンショットのパス
        """
        logger.info(f"インスタンス変更を検出、スクリーンショットを撮影: {instance_id}")

        # 少し待ってからキャプチャ（ワールドの読み込みを待つ）
        time.sleep(2)

        return self.capture_vrchat_window(prefix="vrchat", reason="instance_change")

    def start_auto_capture(self, interval: int = 180) -> None:
        """
        定期的な自動キャプチャを開始
        Args:
            interval: キャプチャ間隔（秒）デフォルト: 180秒（3分）
        """
        if self.is_auto_capture_running:
            logger.warning("既に自動キャプチャが実行中です")
            return

        self.auto_capture_interval = interval
        self._stop_event.clear()
        self.is_auto_capture_running = True

        # 別スレッドで定期キャプチャを実行
        self.auto_capture_thread = threading.Thread(target=self._auto_capture_loop, daemon=True)
        self.auto_capture_thread.start()

        logger.info(f"定期的な自動キャプチャを開始: {interval}秒おき")

    def stop_auto_capture(self) -> None:
        """
        定期的な自動キャプチャを停止
        """
        if not self.is_auto_capture_running:
            logger.warning("自動キャプチャは実行されていません")
            return

        logger.info("定期的な自動キャプチャを停止します")
        self._stop_event.set()
        self.is_auto_capture_running = False

        if self.auto_capture_thread:
            self.auto_capture_thread.join(timeout=5)

        logger.info("定期的な自動キャプチャを停止しました")

    def _auto_capture_loop(self) -> None:
        """
        自動キャプチャのループ（内部メソッド）
        """
        # 最初のキャプチャ（即座に実行）
        screenshot_path = self.capture_vrchat_window(prefix="vrchat", reason="auto")
        if screenshot_path and self.screenshot_callback:
            self.screenshot_callback(screenshot_path, "auto_capture")

        while not self._stop_event.is_set():
            # 指定された間隔だけ待機（1秒ごとにチェック）
            for _ in range(self.auto_capture_interval):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

            # 自動キャプチャを実行
            if not self._stop_event.is_set():
                screenshot_path = self.capture_vrchat_window(prefix="vrchat", reason="auto")
                if screenshot_path and self.screenshot_callback:
                    self.screenshot_callback(screenshot_path, "auto_capture")

    def cleanup_old_screenshots(self, days: int = 7) -> None:
        """
        古いスクリーンショットを削除
        Args:
            days: 保持する日数
        """
        from datetime import timedelta

        if not self.screenshots_dir.exists():
            return

        cutoff_time = datetime.now() - timedelta(days=days)

        # 画像ファイルの拡張子
        image_extensions = ['.png', '.jpg', '.jpeg', '.bmp']

        deleted_count = 0
        for screenshot_file in self.screenshots_dir.iterdir():
            if screenshot_file.suffix.lower() not in image_extensions:
                continue

            try:
                # ファイルの最終更新日時を取得
                file_time = datetime.fromtimestamp(screenshot_file.stat().st_mtime)

                # カットオフ時間より古い場合は削除
                if file_time < cutoff_time:
                    screenshot_file.unlink()
                    deleted_count += 1
            except Exception as e:
                logger.error(f"スクリーンショット削除中にエラー: {screenshot_file.name} - {e}")

        if deleted_count > 0:
            logger.info(f"古いスクリーンショットを{deleted_count}枚削除しました")

    def _capture_to_memory(self) -> Optional[Image.Image]:
        """
        VRChatウィンドウをメモリ上にキャプチャ（ファイル保存なし）
        Returns:
            Optional[Image.Image]: PIL Image オブジェクト（失敗時はNone）
        """
        if not WIN32_AVAILABLE:
            return None

        try:
            # VRChatウィンドウが存在するかチェック
            hwnd = self.find_vrchat_window()
            if not hwnd:
                return None

            # ウィンドウの位置とサイズを取得
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = right - left
            height = bottom - top

            # ウィンドウが最小化されている場合はスキップ
            if width <= 0 or height <= 0:
                return None

            # デバイスコンテキストを取得
            hwndDC = win32gui.GetWindowDC(hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()

            # ビットマップを作成
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)

            # ウィンドウの内容をコピー
            PW_RENDERFULLCONTENT = 0x00000002
            result = windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), PW_RENDERFULLCONTENT)

            # 結果が0の場合、通常のBitBltを試す
            if result == 0:
                result = saveDC.BitBlt(
                    (0, 0), (width, height),
                    mfcDC,
                    (0, 0),
                    win32con.SRCCOPY
                )

            # ビットマップをPIL Imageに変換
            bmpinfo = saveBitMap.GetInfo()
            bmpstr = saveBitMap.GetBitmapBits(True)

            img = Image.frombuffer(
                'RGB',
                (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                bmpstr, 'raw', 'BGRX', 0, 1
            )

            # クリーンアップ
            win32gui.DeleteObject(saveBitMap.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwndDC)

            return img

        except Exception as e:
            logger.debug(f"メモリキャプチャ中にエラー: {e}")
            return None

    def start_avatar_detection(
        self,
        interval: int = 5,
        sensitivity: float = 0.10,
        mode: str = "advanced",
        consecutive_frames: int = 6,
        hold_seconds: float = 6.0,
        flow_min: float = 0.35,
        base_score_threshold: float = 0.45,
        warmup_frames: int = 30
    ) -> None:
        """
        アバター検出機能を開始（5秒ごとにスクリーンを監視）
        Args:
            interval: 監視間隔（秒）デフォルト: 5秒
            sensitivity: 変化検出の感度（0.0～1.0）デフォルト: 0.10（10%）
            mode: 検出モード（"simple" or "advanced"）デフォルト: "advanced"
            consecutive_frames: 連続検出フレーム数（advancedモード）デフォルト: 6
            hold_seconds: 検出後の保持時間（advancedモード）デフォルト: 6.0
            flow_min: Optical Flow最小閾値（advancedモード）デフォルト: 0.35
            base_score_threshold: ベーススコア閾値（advancedモード）デフォルト: 0.45
            warmup_frames: ウォームアップフレーム数（advancedモード）デフォルト: 30
        """
        if self.is_avatar_detection_running:
            logger.warning("既にアバター検出が実行中です")
            return

        # モードに応じた検出器を初期化
        if mode == "advanced":
            if not AVATAR_PRESENCE_DETECTOR_AVAILABLE:
                logger.warning("AvatarPresenceDetectorが利用できません。simpleモードにフォールバックします")
                mode = "simple"
            else:
                self.avatar_detector = AvatarPresenceDetector(
                    sensitivity=sensitivity,
                    consecutive_frames=consecutive_frames,
                    hold_seconds=hold_seconds,
                    flow_min=flow_min,
                    base_score_threshold=base_score_threshold,
                    warmup_frames=warmup_frames
                )
                if not self.avatar_detector.is_available:
                    logger.warning("OpenCVが利用できないため、アバター検出を開始できません")
                    return
                logger.info(f"高精度アバター検出モード: frames={consecutive_frames}, hold={hold_seconds}s, "
                           f"flow_min={flow_min}, base_score={base_score_threshold}, warmup={warmup_frames}")

        if mode == "simple":
            if not AVATAR_DETECTOR_AVAILABLE:
                logger.warning("AvatarDetectorが利用できません")
                return

            self.avatar_detector = AvatarDetector(sensitivity=sensitivity)

            if not self.avatar_detector.is_available:
                logger.warning("OpenCVが利用できないため、アバター検出を開始できません")
                return
            logger.info("シンプルアバター検出モード（フレーム差分）")

        self.avatar_detection_interval = interval
        self._avatar_detection_stop_event.clear()
        self.is_avatar_detection_running = True

        # 別スレッドでアバター検出を実行
        self.avatar_detection_thread = threading.Thread(
            target=self._avatar_detection_loop,
            daemon=True
        )
        self.avatar_detection_thread.start()

        logger.info(f"アバター検出を開始: {interval}秒おき, 感度={sensitivity*100:.1f}%, mode={mode}")

    def stop_avatar_detection(self) -> None:
        """
        アバター検出機能を停止
        """
        if not self.is_avatar_detection_running:
            return

        logger.info("アバター検出を停止します")
        self._avatar_detection_stop_event.set()
        self.is_avatar_detection_running = False

        if self.avatar_detection_thread:
            self.avatar_detection_thread.join(timeout=5)

        # 検出器をリセット
        if self.avatar_detector:
            self.avatar_detector.reset()

        logger.info("アバター検出を停止しました")

    def update_user_count(self, user_count: int) -> None:
        """
        現在のユーザー数を更新（自分を含む総数）
        Args:
            user_count: 現在のユーザー数（自分を含む）
        """
        self.current_user_count = user_count
        logger.debug(f"ユーザー数を更新: {user_count}人")

    def _save_detected_frame(self, detected_frame: Image.Image, reason: str = "avatar_detected") -> Optional[Path]:
        """
        検出されたフレームをファイルに保存

        Args:
            detected_frame: 検出時のPIL Imageフレーム
            reason: 保存理由（ファイル名に含める）

        Returns:
            Path: 保存されたスクリーンショットのパス（失敗時はNone）
        """
        try:
            # ファイル名を生成
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"vrchat_{reason}_{timestamp}.png"
            screenshot_path = self.screenshots_dir / filename

            # PIL Imageとして保存
            detected_frame.save(str(screenshot_path), 'PNG')
            logger.info(f"検出フレームを保存: {filename}")

            return screenshot_path

        except Exception as e:
            logger.error(f"検出フレームの保存中にエラー: {e}")
            return None

    def _avatar_detection_loop(self) -> None:
        """
        アバター検出ループ（内部メソッド）
        5秒ごとにスクリーンをキャプチャして変化を検出
        """
        logger.info("アバター検出ループを開始")

        while not self._avatar_detection_stop_event.is_set():
            try:
                # ユーザー数が1人以下の場合はスキップ（自分しかいない）
                if self.current_user_count <= 1:
                    logger.debug(f"ユーザー数が{self.current_user_count}人のため、アバター検出をスキップ")
                    self._avatar_detection_stop_event.wait(self.avatar_detection_interval)
                    continue

                # メモリ上にキャプチャ（ファイル保存なし）
                image = self._capture_to_memory()

                if image and self.avatar_detector:
                    # 変化検出
                    is_changed, change_ratio = self.avatar_detector.detect_change(image)

                    # デバッグ情報から初回検出フラグを取得
                    debug_info = self.avatar_detector.get_debug_info()
                    newly_detected = debug_info.get('newly_detected', False)

                    # 初回検出時のみスクリーンショットを保存
                    if is_changed and newly_detected:
                        logger.info(f"アバター出現を検出！変化率: {change_ratio*100:.2f}%")

                        # 検出時のフレームを取得
                        detected_frame = self.avatar_detector.get_detected_frame()

                        if detected_frame:
                            # 検出したフレームそのものを保存
                            screenshot_path = self._save_detected_frame(detected_frame, "avatar_detected")
                        else:
                            # フレームが取得できない場合は通常のキャプチャ
                            logger.warning("検出フレームが取得できませんでした。通常キャプチャを実行します")
                            screenshot_path = self.capture_vrchat_window(
                                prefix="vrchat",
                                reason="avatar_detected"
                            )

                        # コールバックを実行
                        if screenshot_path and self.screenshot_callback:
                            self.screenshot_callback(screenshot_path, "avatar_detected")

            except Exception as e:
                logger.error(f"アバター検出ループ中にエラー: {e}")
                import traceback
                traceback.print_exc()

            # 指定された間隔だけ待機
            for _ in range(self.avatar_detection_interval):
                if self._avatar_detection_stop_event.is_set():
                    return
                time.sleep(1)

        logger.info("アバター検出ループを終了")


# 使用例とドキュメント
"""
使用例:

from pathlib import Path
from submodules.screenshot import ScreenshotCapture

# スクリーンショットキャプチャインスタンスを作成
logs_dir = Path("./logs")
capture = ScreenshotCapture(logs_dir)

# インスタンス変更時にキャプチャ
capture.capture_on_instance_change(instance_id="wrld_xxx:12345", world_name="My World")

# 定期的な自動キャプチャを開始（3分おき）
capture.start_auto_capture(interval=180)

# ... VRChatプレイ中 ...

# 自動キャプチャを停止
capture.stop_auto_capture()

# 古いスクリーンショットのクリーンアップ
capture.cleanup_old_screenshots(days=7)


必要な依存関係:
- Windows環境が必要
- PowerShellが利用可能である必要がある
- System.Windows.Forms と System.Drawing アセンブリ

スクリーンショットの保存場所:
- logs/screenshots/vrchat_instance_change_YYYYMMDD_HHMMSS.png
- logs/screenshots/vrchat_auto_YYYYMMDD_HHMMSS.png

注意事項:
- VRChatがフルスクリーンモードの場合、画面全体をキャプチャします
- ウィンドウモードの場合も画面全体をキャプチャします
- より精密なウィンドウキャプチャが必要な場合は、pywin32 を使用した実装を検討してください
"""
