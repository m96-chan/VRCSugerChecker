#!/usr/bin/env python3
"""
File Upload モジュール
0x0.st を使用してファイルをアップロードする機能

機能:
- フォルダ構造を保持したZIP圧縮
- パスワード保護付きZIP
- 0x0.st へのアップロード（最大512MB、7日間保持）
- リトライ機能
"""
import logging
import requests
import zipfile
import pyminizip
import secrets
import string
import shutil
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class FileUploader:
    """0x0.st アップローダークラス"""

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

        # エラーレスポンス保存用ディレクトリ
        self.upload_error_dir = logs_dir / "upload_errors"
        self.upload_error_dir.mkdir(parents=True, exist_ok=True)

        # 0x0.st API エンドポイント
        self.upload_api = "https://0x0.st"

    def get_all_uploadable_files(self) -> Dict[str, List[Path]]:
        """
        アップロード対象のすべてのファイルを取得（フォルダ別に整理）
        Returns:
            Dict[folder_name, [file_paths]]: フォルダ名毎のファイルリスト
        """
        all_files = {}

        # 音声ファイルを取得
        if self.audio_dir.exists():
            audio_files = [f for f in self.audio_dir.glob("*.m4a") if f.is_file()]
            if audio_files:
                all_files["audio"] = audio_files
                logger.info(f"Found {len(audio_files)} audio files")

        # スクリーンショットを取得
        if self.screenshots_dir.exists():
            screenshot_files = [f for f in self.screenshots_dir.glob("*.png") if f.is_file()]
            if screenshot_files:
                all_files["screenshots"] = screenshot_files
                logger.info(f"Found {len(screenshot_files)} screenshot files")

        # ログファイルを取得
        log_files = self._get_log_files()
        if log_files:
            all_files["logs"] = log_files
            logger.info(f"Found {len(log_files)} log files")

        return all_files

    def _generate_password(self, length: int = 16) -> str:
        """
        ランダムなパスワードを生成
        Args:
            length: パスワードの長さ
        Returns:
            str: 生成されたパスワード
        """
        # 英数字と記号を使用
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        logger.info(f"Generated password with length {length}")
        return password

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

    def create_single_archive(
        self, all_files: Dict[str, List[Path]], password: str, date_str: Optional[str] = None
    ) -> Optional[Path]:
        """
        すべてのファイルをパスワード保護付きの1つのZIPアーカイブにまとめる
        Args:
            all_files: フォルダ毎のファイル辞書 {"audio": [...], "screenshots": [...], "logs": [...]}
            password: ZIPファイルのパスワード
            date_str: 日付文字列（オプション、デフォルトは今日）
        Returns:
            Optional[Path]: 作成されたZIPファイルのパス
        """
        if not all_files:
            logger.warning("No files to archive")
            return None

        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")

        # ZIPファイル名: VRChat_Session_YYYYMMDD.zip
        zip_filename = f"VRChat_Session_{date_str}.zip"
        zip_path = self.upload_temp_dir / zip_filename

        try:
            total_files = sum(len(files) for files in all_files.values())
            logger.info(f"Creating password-protected archive with {total_files} files...")

            # pyminizipで圧縮するファイルリストを準備
            file_list = []
            arcname_list = []

            for folder_name, files in all_files.items():
                for file in files:
                    file_list.append(str(file))
                    # ZIP内のパス: フォルダ構造を保持
                    arcname = f"{folder_name}/{file.name}"
                    arcname_list.append(arcname)
                    logger.debug(f"Will add to ZIP: {arcname}")

            # pyminizipでパスワード保護付きZIPを作成
            # compression_level: 0-9 (0=無圧縮, 9=最大圧縮)
            pyminizip.compress_multiple(
                file_list,
                arcname_list,
                str(zip_path),
                password,
                5  # 圧縮レベル5(標準)
            )

            file_size_mb = zip_path.stat().st_size / (1024 * 1024)
            logger.info(f"Created password-protected archive: {zip_filename} ({file_size_mb:.2f} MB, {total_files} files)")
            return zip_path

        except Exception as e:
            logger.error(f"Failed to create archive: {e}")
            import traceback
            traceback.print_exc()
            if zip_path.exists():
                zip_path.unlink()
            return None

    def _save_error_response(self, response_text: str, status_code: int, attempt: int) -> Path:
        """
        エラーレスポンスをファイルに保存
        Args:
            response_text: レスポンス本文
            status_code: HTTPステータスコード
            attempt: 試行回数
        Returns:
            Path: 保存したファイルのパス
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        error_filename = f"upload_error_{timestamp}_status{status_code}_attempt{attempt}.html"
        error_file = self.upload_error_dir / error_filename

        try:
            with open(error_file, 'w', encoding='utf-8') as f:
                f.write(f"<!-- Status Code: {status_code} -->\n")
                f.write(f"<!-- Attempt: {attempt} -->\n")
                f.write(f"<!-- Timestamp: {timestamp} -->\n\n")
                f.write(response_text)

            logger.info(f"エラーレスポンスを保存: {error_file.name}")
            return error_file
        except Exception as e:
            logger.error(f"エラーレスポンスの保存に失敗: {e}")
            return None

    def upload_to_0x0st(
        self, file_path: Path, expires: int = 168, max_retries: int = 3
    ) -> Optional[Dict[str, str]]:
        """
        0x0.st にファイルをアップロード
        Args:
            file_path: アップロードするファイルのパス
            expires: 保持時間（時間単位、デフォルト168時間=7日）
            max_retries: 最大リトライ回数
        Returns:
            Optional[Dict]: アップロード結果 {"success": True, "link": "..."}
        """
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        file_size_mb = file_path.stat().st_size / (1024 * 1024)

        # 0x0.stの最大ファイルサイズは512MB
        if file_size_mb > 512:
            logger.error(f"File too large: {file_size_mb:.2f} MB (max 512 MB)")
            return None

        logger.info(f"Uploading {file_path.name} ({file_size_mb:.2f} MB) to 0x0.st...")

        for attempt in range(1, max_retries + 1):
            try:
                # 0x0.stはシンプルなPOSTリクエスト
                with open(file_path, 'rb') as f:
                    files = {
                        'file': (file_path.name, f, 'application/octet-stream')
                    }

                    # expiresパラメータで保持時間を指定（時間単位）
                    data = {
                        'expires': str(expires)
                    }

                    response = requests.post(
                        self.upload_api,
                        files=files,
                        data=data,
                        timeout=600  # 10分タイムアウト（大きなファイル用）
                    )

                    # レスポンスのデバッグ情報を出力
                    logger.info(f"Response status: {response.status_code}")

                    # 0x0.stは200番台で成功、レスポンスはダウンロードURLのテキスト
                    if 200 <= response.status_code < 300:
                        download_url = response.text.strip()
                        logger.info(f"Upload successful: {download_url}")
                        return {
                            'success': True,
                            'link': download_url,
                            'file_name': file_path.name,
                            'file_size_mb': file_size_mb,
                            'expires_hours': expires
                        }
                    else:
                        logger.error(f"Upload failed with status {response.status_code}")
                        logger.error(f"Response content: {response.text[:500]}")

                        # エラーレスポンスをファイルに保存
                        error_file = self._save_error_response(response.text, response.status_code, attempt)
                        if error_file:
                            logger.error(f"完全なレスポンスを確認してください: {error_file}")

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
        self, expires_hours: int = 168, cleanup: bool = True
    ) -> Tuple[List[Dict[str, str]], Optional[str]]:
        """
        すべてのファイルを1つのパスワード保護ZIPにまとめてアップロード
        Args:
            expires_hours: 0x0.stの保持時間（時間単位、デフォルト168時間=7日）
            cleanup: アップロード後にファイルを削除するか
        Returns:
            Tuple[List[Dict], Optional[str]]: (アップロード結果のリスト, ZIPパスワード)
        """
        logger.info("Starting file upload process...")

        # 1. アップロード対象のすべてのファイルを取得
        all_files = self.get_all_uploadable_files()
        if not all_files:
            logger.info("No files to upload")
            return [], None

        total_files = sum(len(files) for files in all_files.values())
        logger.info(f"Found {total_files} files to upload")

        # 2. ランダムなパスワードを生成
        password = self._generate_password(16)

        # 3. パスワード保護付きZIPアーカイブを作成
        archive_path = self.create_single_archive(all_files, password)
        if not archive_path:
            logger.warning("Failed to create archive")
            return [], None

        # 4. 0x0.stにアップロード
        upload_results = []
        result = self.upload_to_0x0st(archive_path, expires=expires_hours)
        if result:
            # パスワードを結果に追加
            result['password'] = password
            upload_results.append(result)

            # 5. クリーンアップ
            if cleanup:
                self._cleanup_uploaded_files(all_files, archive_path)
        else:
            logger.error("Upload failed")

        return upload_results, password if upload_results else None

    def _cleanup_uploaded_files(
        self, all_files: Dict[str, List[Path]], archive_path: Path
    ) -> None:
        """
        アップロード済みファイルを削除（ログファイルは除外）
        Args:
            all_files: フォルダ毎のファイル辞書
            archive_path: 作成したZIPファイルのパス
        """
        # 元のファイルを削除（ログファイルは除外）
        for folder_name, files in all_files.items():
            # "logs" フォルダのファイルは削除しない
            if folder_name == "logs":
                logger.info(f"Skipping deletion of {len(files)} log files")
                continue

            deleted_count = 0
            for file in files:
                try:
                    file.unlink()
                    deleted_count += 1
                    logger.debug(f"Deleted: {file.name}")
                except Exception as e:
                    logger.error(f"Failed to delete {file.name}: {e}")

            logger.info(f"Deleted {deleted_count} files from {folder_name}/")

        # ZIPファイルを削除
        try:
            archive_path.unlink()
            logger.info(f"Deleted archive: {archive_path.name}")
        except Exception as e:
            logger.error(f"Failed to delete archive {archive_path.name}: {e}")

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

    def cleanup_old_error_files(self, days: int = 7) -> None:
        """
        古いエラーレスポンスファイルを削除
        Args:
            days: 保持する日数
        """
        if not self.upload_error_dir.exists():
            return

        cutoff_time = datetime.now() - timedelta(days=days)
        deleted_count = 0

        for error_file in self.upload_error_dir.iterdir():
            # .gitkeepは除外
            if error_file.name == ".gitkeep":
                continue

            try:
                file_time = datetime.fromtimestamp(error_file.stat().st_mtime)
                if file_time < cutoff_time:
                    error_file.unlink()
                    deleted_count += 1
                    logger.debug(f"古いエラーファイルを削除: {error_file.name}")
            except Exception as e:
                logger.error(f"エラーファイル削除中にエラー: {error_file.name} - {e}")

        if deleted_count > 0:
            logger.info(f"古いエラーファイルを{deleted_count}個削除しました")
