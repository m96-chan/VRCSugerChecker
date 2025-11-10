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
from typing import Optional, Tuple
import subprocess

logger = logging.getLogger(__name__)


class ScreenshotCapture:
    """スクリーンショット撮影クラス"""

    def __init__(self, logs_dir: Path):
        """
        初期化
        Args:
            logs_dir: ログディレクトリのパス（スクリーンショット保存先）
        """
        self.logs_dir = logs_dir
        self.is_auto_capture_running = False
        self.auto_capture_thread: Optional[threading.Thread] = None
        self.auto_capture_interval = 180  # 3分 = 180秒
        self._stop_event = threading.Event()

        # スクリーンショット保存用のサブディレクトリを作成
        self.screenshots_dir = logs_dir / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    def find_vrchat_window(self) -> bool:
        """
        VRChatウィンドウを検索
        Returns:
            bool: VRChatウィンドウが見つかった場合True
        """
        try:
            # PowerShell経由でVRChatウィンドウを検索
            result = subprocess.run(
                ["powershell.exe", "-Command",
                 "Get-Process -Name VRChat -ErrorAction SilentlyContinue | Select-Object -First 1 MainWindowHandle"],
                capture_output=True,
                text=True,
                timeout=5
            )

            # ウィンドウハンドルが存在するかチェック
            output = result.stdout.strip()
            if output and "MainWindowHandle" in output:
                lines = output.split('\n')
                if len(lines) > 2:  # ヘッダー行をスキップ
                    handle_line = lines[2].strip()
                    if handle_line and handle_line != "0":
                        return True

            return False
        except Exception as e:
            logger.error(f"VRChatウィンドウの検索中にエラー: {e}")
            return False

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
            if not self.find_vrchat_window():
                logger.warning("VRChatウィンドウが見つかりません")
                return None

            # ファイル名を生成
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if reason:
                filename = f"{prefix}_{reason}_{timestamp}.png"
            else:
                filename = f"{prefix}_{timestamp}.png"

            screenshot_path = self.screenshots_dir / filename

            # PowerShellスクリプトでスクリーンショットを撮影
            # Add-Type でWindows APIを使用してVRChatウィンドウをキャプチャ
            ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# VRChatプロセスを取得
$process = Get-Process -Name "VRChat" -ErrorAction SilentlyContinue | Select-Object -First 1

if ($process -eq $null) {{
    Write-Host "VRChat process not found"
    exit 1
}}

# ウィンドウハンドルを取得
$hwnd = $process.MainWindowHandle

if ($hwnd -eq 0) {{
    Write-Host "VRChat window not found"
    exit 1
}}

# ウィンドウを前面に表示（オプション、コメントアウト可）
# [void][System.Reflection.Assembly]::LoadWithPartialName("Microsoft.VisualBasic")
# [Microsoft.VisualBasic.Interaction]::AppActivate($process.Id)
# Start-Sleep -Milliseconds 500

# 画面全体をキャプチャ（VRChatがフルスクリーンの場合）
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)

# ファイルに保存
$bitmap.Save("{str(screenshot_path).replace(chr(92), chr(92)*2)}", [System.Drawing.Imaging.ImageFormat]::Png)

# クリーンアップ
$graphics.Dispose()
$bitmap.Dispose()

Write-Host "Screenshot saved: {filename}"
"""

            # PowerShellスクリプトを実行
            result = subprocess.run(
                ["powershell.exe", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0 and screenshot_path.exists():
                logger.info(f"スクリーンショットを保存: {filename}")
                return screenshot_path
            else:
                logger.error(f"スクリーンショットの保存に失敗: {result.stderr}")
                return None

        except Exception as e:
            logger.error(f"スクリーンショットのキャプチャ中にエラー: {e}")
            return None

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
        self.capture_vrchat_window(prefix="vrchat", reason="auto")

        while not self._stop_event.is_set():
            # 指定された間隔だけ待機（1秒ごとにチェック）
            for _ in range(self.auto_capture_interval):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

            # 自動キャプチャを実行
            if not self._stop_event.is_set():
                self.capture_vrchat_window(prefix="vrchat", reason="auto")

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
