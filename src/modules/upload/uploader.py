#!/usr/bin/env python3
"""
File Upload モジュール
file.io を使用してファイルをアップロードする機能

機能:
- ワールド毎のフォルダ整理
- ZIP圧縮
- file.io へのアップロード
- リトライ機能
"""
import logging
import requests
import zipfile
import shutil
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class FileUploader:
    """file.io アップローダークラス"""

    def __init__(self, logs_dir: Path):
        """
        初期化
        Args:
            logs_dir: ログディレクトリのパス
        """
        self.logs_dir = logs_dir
        self.audio_dir = logs_dir / "audio"
        self.screenshots_dir = logs_dir / "screenshots"
        self.upload_temp_dir = logs_dir / "upload_temp"
        self.upload_temp_dir.mkdir(parents=True, exist_ok=True)

        # file.io API エンドポイント
        self.fileio_api = "https://file.io"

    def organize_files_by_world(self) -> Dict[str, List[Path]]:
        """
        音声ファイル、スクリーンショット、ログファイルをワールド毎に整理
        Returns:
            Dict[world_id, [file_paths]]: ワールドID毎のファイルリスト
        """
        world_files = defaultdict(list)

        # 音声ファイルを整理
        # ファイル名形式: worldID-YYYYMMDD_HHMMSS.m4a
        if self.audio_dir.exists():
            for audio_file in self.audio_dir.glob("*.m4a"):
                world_id = self._extract_world_id_from_audio(audio_file.name)
                if world_id:
                    world_files[world_id].append(audio_file)

        # スクリーンショットを整理
        # ファイル名形式: vrchat_*_YYYYMMDD_HHMMSS.png
        if self.screenshots_dir.exists():
            for screenshot in self.screenshots_dir.glob("*.png"):
                # スクリーンショットは時間帯でグルーピング
                # 音声ファイルと同じワールドのものを紐付ける（タイムスタンプベース）
                world_id = self._match_screenshot_to_world(screenshot, world_files)
                if world_id:
                    world_files[world_id].append(screenshot)
                else:
                    # マッチしない場合は "screenshots" グループに入れる
                    world_files["screenshots"].append(screenshot)

        # ログファイルを整理（すべてのアーカイブに含める）
        log_files = self._get_log_files()
        if log_files:
            # "logs" グループに全ログファイルを追加
            world_files["logs"] = log_files

        return dict(world_files)

    def _extract_world_id_from_audio(self, filename: str) -> Optional[str]:
        """
        音声ファイル名からワールドIDを抽出
        Args:
            filename: ファイル名
        Returns:
            Optional[str]: ワールドID
        """
        # ファイル名形式: worldID-YYYYMMDD_HHMMSS.m4a
        match = re.match(r'^(.+?)-\d{8}_\d{6}\.m4a$', filename)
        if match:
            return match.group(1)
        return None

    def _match_screenshot_to_world(
        self, screenshot: Path, world_files: Dict[str, List[Path]]
    ) -> Optional[str]:
        """
        スクリーンショットを音声ファイルのワールドにマッチング
        Args:
            screenshot: スクリーンショットのパス
            world_files: ワールド毎のファイル辞書
        Returns:
            Optional[str]: マッチしたワールドID
        """
        # スクリーンショットのタイムスタンプを抽出
        # ファイル名形式: vrchat_*_YYYYMMDD_HHMMSS.png
        match = re.search(r'(\d{8}_\d{6})\.png$', screenshot.name)
        if not match:
            return None

        screenshot_timestamp_str = match.group(1)
        try:
            screenshot_time = datetime.strptime(screenshot_timestamp_str, "%Y%m%d_%H%M%S")
        except ValueError:
            return None

        # 各ワールドの音声ファイルと時間比較（前後5分以内）
        for world_id, files in world_files.items():
            for file in files:
                if file.suffix == '.m4a':
                    # 音声ファイルのタイムスタンプを抽出
                    audio_match = re.search(r'(\d{8}_\d{6})\.m4a$', file.name)
                    if audio_match:
                        try:
                            audio_time = datetime.strptime(audio_match.group(1), "%Y%m%d_%H%M%S")
                            # 前後5分以内ならマッチ
                            if abs((screenshot_time - audio_time).total_seconds()) <= 300:
                                return world_id
                        except ValueError:
                            continue

        return None

    def _get_log_files(self) -> List[Path]:
        """
        アップロード対象のログファイルを取得
        Returns:
            List[Path]: ログファイルのリスト
        """
        log_files = []

        # .logファイルを検索（ローテーション済みログも含む）
        # 例: vrchat_checker.log, vrchat_checker.log.20231111
        if self.logs_dir.exists():
            for log_file in self.logs_dir.glob("*.log*"):
                # .gitkeepは除外
                if log_file.name == ".gitkeep":
                    continue
                # ディレクトリは除外
                if log_file.is_file():
                    log_files.append(log_file)

        logger.info(f"Found {len(log_files)} log files to include in upload")
        return log_files

    def create_world_archives(
        self, world_files: Dict[str, List[Path]], date_str: Optional[str] = None
    ) -> List[Tuple[str, Path]]:
        """
        ワールド毎にZIPアーカイブを作成
        Args:
            world_files: ワールド毎のファイル辞書
            date_str: 日付文字列（オプション、デフォルトは今日）
        Returns:
            List[Tuple[world_id, zip_path]]: ワールドIDとZIPファイルパスのリスト
        """
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")

        archives = []

        for world_id, files in world_files.items():
            if not files:
                continue

            # ワールドIDを安全なファイル名に変換
            safe_world_id = self._sanitize_filename(world_id)

            # ZIPファイル名: worldID_YYYYMMDD.zip
            zip_filename = f"{safe_world_id}_{date_str}.zip"
            zip_path = self.upload_temp_dir / zip_filename

            try:
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file in files:
                        # ZIP内のパス: ワールドID/ファイル名
                        arcname = f"{safe_world_id}/{file.name}"
                        zipf.write(file, arcname=arcname)
                        logger.debug(f"Added to ZIP: {file.name} -> {arcname}")

                file_size_mb = zip_path.stat().st_size / (1024 * 1024)
                logger.info(f"Created archive: {zip_filename} ({file_size_mb:.2f} MB, {len(files)} files)")
                archives.append((world_id, zip_path))

            except Exception as e:
                logger.error(f"Failed to create archive for {world_id}: {e}")
                if zip_path.exists():
                    zip_path.unlink()

        return archives

    def upload_to_fileio(
        self, file_path: Path, expires: str = "1w", max_retries: int = 3
    ) -> Optional[Dict[str, str]]:
        """
        file.io にファイルをアップロード
        Args:
            file_path: アップロードするファイルのパス
            expires: 有効期限（1d, 1w, 1m, 1y）
            max_retries: 最大リトライ回数
        Returns:
            Optional[Dict]: アップロード結果 {"success": True, "link": "...", "key": "..."}
        """
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        logger.info(f"Uploading {file_path.name} ({file_size_mb:.2f} MB) to file.io...")

        for attempt in range(1, max_retries + 1):
            try:
                with open(file_path, 'rb') as f:
                    files = {'file': (file_path.name, f)}
                    data = {'expires': expires}

                    response = requests.post(
                        self.fileio_api,
                        files=files,
                        data=data,
                        timeout=300  # 5分タイムアウト
                    )

                    if response.status_code == 200:
                        result = response.json()
                        if result.get('success'):
                            link = result.get('link')
                            key = result.get('key')
                            logger.info(f"Upload successful: {link}")
                            return {
                                'success': True,
                                'link': link,
                                'key': key,
                                'file_name': file_path.name,
                                'file_size_mb': file_size_mb
                            }
                        else:
                            logger.error(f"Upload failed: {result.get('message', 'Unknown error')}")
                    else:
                        logger.error(f"Upload failed with status {response.status_code}: {response.text}")

            except requests.exceptions.Timeout:
                logger.warning(f"Upload timeout (attempt {attempt}/{max_retries})")
            except Exception as e:
                logger.error(f"Upload error (attempt {attempt}/{max_retries}): {e}")

            # リトライ前に少し待つ
            if attempt < max_retries:
                import time
                time.sleep(2 ** attempt)  # 指数バックオフ: 2, 4, 8秒

        logger.error(f"Upload failed after {max_retries} attempts")
        return None

    def process_and_upload_all(
        self, expires: str = "1w", cleanup: bool = True
    ) -> List[Dict[str, str]]:
        """
        すべてのファイルを処理してアップロード
        Args:
            expires: file.io の有効期限
            cleanup: アップロード後にファイルを削除するか
        Returns:
            List[Dict]: アップロード結果のリスト
        """
        logger.info("Starting file upload process...")

        # 1. ファイルをワールド毎に整理
        world_files = self.organize_files_by_world()
        if not world_files:
            logger.info("No files to upload")
            return []

        logger.info(f"Organized files into {len(world_files)} groups")

        # 2. ZIPアーカイブを作成
        archives = self.create_world_archives(world_files)
        if not archives:
            logger.warning("No archives created")
            return []

        # 3. アップロード
        upload_results = []
        for world_id, zip_path in archives:
            result = self.upload_to_fileio(zip_path, expires=expires)
            if result:
                result['world_id'] = world_id
                upload_results.append(result)

        # 4. クリーンアップ
        if cleanup and upload_results:
            self._cleanup_uploaded_files(world_files, archives)

        return upload_results

    def _cleanup_uploaded_files(
        self, world_files: Dict[str, List[Path]], archives: List[Tuple[str, Path]]
    ) -> None:
        """
        アップロード済みファイルを削除（ログファイルは除外）
        Args:
            world_files: ワールド毎のファイル辞書
            archives: アーカイブのリスト
        """
        # 元のファイルを削除（ログファイルは除外）
        for world_id, files in world_files.items():
            # "logs" グループのファイルは削除しない
            if world_id == "logs":
                logger.info(f"Skipping deletion of {len(files)} log files")
                continue

            for file in files:
                try:
                    file.unlink()
                    logger.debug(f"Deleted: {file.name}")
                except Exception as e:
                    logger.error(f"Failed to delete {file.name}: {e}")

        # ZIPファイルを削除
        for _, zip_path in archives:
            try:
                zip_path.unlink()
                logger.debug(f"Deleted archive: {zip_path.name}")
            except Exception as e:
                logger.error(f"Failed to delete archive {zip_path.name}: {e}")

    def _sanitize_filename(self, name: str) -> str:
        """
        ファイル名に使用できない文字を削除
        Args:
            name: 元のファイル名
        Returns:
            str: 安全なファイル名
        """
        # Windows/Linuxで使用できない文字を削除
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        # 連続するスペースを1つに
        name = re.sub(r'\s+', '_', name)
        # 先頭・末尾のスペースやドットを削除
        name = name.strip(' .')
        # 最大長を制限（200文字）
        if len(name) > 200:
            name = name[:200]
        return name

    def should_upload_daily(self, last_upload_date: Optional[str]) -> bool:
        """
        日次アップロードが必要かチェック
        Args:
            last_upload_date: 最後のアップロード日（YYYYMMDD形式）
        Returns:
            bool: アップロードが必要な場合True
        """
        if not last_upload_date:
            return True

        try:
            last_date = datetime.strptime(last_upload_date, "%Y%m%d")
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            return last_date.date() < today.date()
        except ValueError:
            return True
