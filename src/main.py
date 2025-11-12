#!/usr/bin/env python3
"""
VRChat Sugar Checker
VRChat.exeのプロセスを監視し、起動時にログ監視を開始、終了時に停止します
"""
import subprocess
import time
import sys
import argparse
import logging
import json
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict
from logging.handlers import TimedRotatingFileHandler

# modulesのparse_logs.pyをインポート
sys.path.insert(0, str(Path(__file__).parent / "modules" / "vrc"))
sys.path.insert(0, str(Path(__file__).parent / "modules"))
import parse_logs
from discord.webhook import DiscordWebhook
from screenshot.capture import ScreenshotCapture
from audio.recorder import AudioRecorder
from upload.uploader import FileUploader

# AI画像分析のインポート（オプショナル）
try:
    from ai.image_analyzer import ImageAnalyzer
    IMAGE_ANALYZER_AVAILABLE = True
except ImportError:
    IMAGE_ANALYZER_AVAILABLE = False

# AI音声分析のインポート（オプショナル）
try:
    from ai.audio_analyzer import AudioAnalyzer
    AUDIO_ANALYZER_AVAILABLE = True
except ImportError:
    AUDIO_ANALYZER_AVAILABLE = False

# ロガー設定
logger = logging.getLogger(__name__)

# グローバル変数
discord_webhook: Optional[DiscordWebhook] = None
screenshot_capture: Optional[ScreenshotCapture] = None
audio_recorder: Optional[AudioRecorder] = None
file_uploader: Optional[FileUploader] = None
image_analyzer: Optional['ImageAnalyzer'] = None
audio_analyzer: Optional['AudioAnalyzer'] = None
config: Dict = {}
last_instance_id: Optional[str] = None
last_users: Dict[str, str] = {}
last_world_name: Optional[str] = None
last_upload_date: Optional[str] = None  # 最後のアップロード日（YYYYMMDD形式）


def setup_logging(logs_dir: Path) -> None:
    """
    ログ設定をセットアップ（7日間ローテーション）
    Args:
        logs_dir: ログディレクトリのパス
    """
    # logsディレクトリが存在しない場合は作成
    logs_dir.mkdir(parents=True, exist_ok=True)

    # ログファイルのパス
    log_file = logs_dir / "vrchat_checker.log"

    # フォーマット設定
    log_format = '%(asctime)s [%(levelname)s] %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter(log_format, date_format)

    # ルートロガーの設定
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # 既存のハンドラーをクリア
    root_logger.handlers.clear()

    # ファイルハンドラー（7日間ローテーション）
    # when='midnight': 毎日真夜中にローテーション
    # interval=1: 1日ごと
    # backupCount=7: 7日分のバックアップを保持
    file_handler = TimedRotatingFileHandler(
        filename=str(log_file),
        when='midnight',
        interval=1,
        backupCount=7,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.suffix = "%Y%m%d"  # ローテーション時のファイル名に日付を追加
    root_logger.addHandler(file_handler)

    # コンソールハンドラー
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    logger.info(f"ログファイル: {log_file}")
    logger.info("ログローテーション: 7日間（毎日真夜中）")


def cleanup_old_logs(logs_dir: Path, days: int = 7) -> None:
    """
    古いログファイルを削除
    Args:
        logs_dir: ログディレクトリのパス
        days: 保持する日数
    """
    if not logs_dir.exists():
        return

    cutoff_time = datetime.now() - timedelta(days=days)

    for log_file in logs_dir.glob("*.log*"):
        # .gitkeepは除外
        if log_file.name == ".gitkeep":
            continue

        try:
            # ファイルの最終更新日時を取得
            file_time = datetime.fromtimestamp(log_file.stat().st_mtime)

            # カットオフ時間より古い場合は削除
            if file_time < cutoff_time:
                log_file.unlink()
                logger.info(f"古いログファイルを削除: {log_file.name}")
        except Exception as e:
            logger.error(f"ログファイル削除中にエラー: {log_file.name} - {e}")


def load_config(config_path: Path) -> Dict:
    """
    設定ファイルを読み込む
    Args:
        config_path: 設定ファイルのパス
    Returns:
        Dict: 設定内容
    """
    default_config = {
        "discord": {
            "enabled": False,
            "webhook_url": "",
            "username": "VRChat Sugar Checker",
            "avatar_url": "",
            "notifications": {
                "vrchat_started": True,
                "vrchat_stopped": True,
                "instance_info": True,
                "instance_changed": True,
                "user_joined": False,
                "user_left": False
            }
        },
        "monitoring": {
            "check_interval": 5,
            "log_update_interval": 30
        }
    }

    if not config_path.exists():
        logger.warning(f"設定ファイルが見つかりません: {config_path}")
        logger.info("デフォルト設定を使用します")
        return default_config

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            loaded_config = json.load(f)
        logger.info(f"設定ファイルを読み込みました: {config_path}")
        return loaded_config
    except Exception as e:
        logger.error(f"設定ファイルの読み込みに失敗: {e}")
        logger.info("デフォルト設定を使用します")
        return default_config


def is_vrchat_running():
    """
    VRChat.exeが起動しているかをチェック
    Returns:
        bool: VRChat.exeが起動している場合True
    """
    try:
        # PowerShell経由でVRChat.exeプロセスをチェック
        result = subprocess.run(
            ["powershell.exe", "-Command", "Get-Process -Name VRChat -ErrorAction SilentlyContinue"],
            capture_output=True,
            text=True,
            timeout=5
        )
        # プロセスが存在する場合、出力に "VRChat" が含まれる
        return "VRChat" in result.stdout
    except Exception as e:
        logger.error(f"プロセスチェック中にエラーが発生: {e}")
        return False


def monitor_vrchat_process(check_interval=5):
    """
    VRChat.exeのプロセスを監視し、起動/終了に応じて処理を実行
    Args:
        check_interval: プロセスチェックの間隔（秒）
    """
    global last_instance_id, last_users, last_upload_date

    print("="*60)
    print("VRChat Sugar Checker 起動")
    print("="*60)
    print(f"VRChat.exeの起動を監視中... ({check_interval}秒間隔)")
    print("終了するには Ctrl+C を押してください\n")

    vrchat_was_running = False
    log_monitoring_active = False
    last_daily_check = datetime.now().date()

    try:
        while True:
            vrchat_is_running = is_vrchat_running()

            # 日次チェック（日をまたいだ場合のアップロード）
            current_date = datetime.now().date()
            if current_date > last_daily_check:
                last_daily_check = current_date
                upload_config = config.get("upload", {})
                if upload_config.get("enabled", False) and upload_config.get("daily_upload", True):
                    if file_uploader and file_uploader.should_upload_daily(last_upload_date):
                        logger.info("Daily upload triggered (date changed)")
                        upload_files_to_cloud()

            # VRChatが起動した場合
            if vrchat_is_running and not vrchat_was_running:
                print("\n" + "="*60)
                print("[検出] VRChat.exe が起動しました！")
                print("="*60)
                log_monitoring_active = True

                # Discord通知
                if discord_webhook and config.get("discord", {}).get("notifications", {}).get("vrchat_started", False):
                    discord_webhook.send_vrchat_started()

                start_log_monitoring()

            # VRChatが終了した場合
            elif not vrchat_is_running and vrchat_was_running:
                print("\n" + "="*60)
                print("[検出] VRChat.exe が終了しました")
                print("="*60)
                log_monitoring_active = False

                # Discord通知
                if discord_webhook and config.get("discord", {}).get("notifications", {}).get("vrchat_stopped", False):
                    discord_webhook.send_vrchat_stopped()

                stop_log_monitoring()

                # ファイルアップロード（VRChat終了時）
                upload_config = config.get("upload", {})
                if upload_config.get("enabled", False) and upload_config.get("upload_on_exit", True):
                    upload_files_to_cloud()

                print(f"\nVRChat.exeの起動を監視中... ({check_interval}秒間隔)")

                # リセット
                last_instance_id = None
                last_users = {}

                # アバター検出のユーザー数をリセット
                if screenshot_capture:
                    screenshot_capture.update_user_count(0)

            # ログ監視が有効な場合、ログを定期的に更新
            elif log_monitoring_active:
                update_log_monitoring()

            vrchat_was_running = vrchat_is_running
            time.sleep(check_interval)

    except KeyboardInterrupt:
        print("\n\n" + "="*60)
        print("監視を終了します")
        print("="*60)
        if log_monitoring_active:
            stop_log_monitoring()


def start_log_monitoring():
    """
    ログ監視を開始
    """
    global last_instance_id, last_users, last_world_name

    print("[動作開始] VRChatログの監視を開始します\n")
    try:
        # ログディレクトリを取得
        log_dir = parse_logs.get_vrchat_log_directory()
        print(f"[INFO] ログディレクトリ: {log_dir}")

        # 最新のログファイルを取得
        log_file = parse_logs.get_latest_log_file(log_dir)
        print(f"[INFO] 監視中のログファイル: {log_file.name}\n")

        # 初回のログ解析
        result = parse_logs.parse_vrchat_log(log_file)
        parse_logs.display_results(result)

        # マイクデバイスを設定
        if audio_recorder and result.get('microphone_device'):
            audio_recorder.set_mic_device(result['microphone_device'])
            logger.info(f"マイクデバイスを検出: {result['microphone_device']}")

        # Discord通知（インスタンス情報）
        if discord_webhook and config.get("discord", {}).get("notifications", {}).get("instance_info", False):
            if result['current_instance']:
                discord_webhook.send_instance_info(
                    instance_id=result['current_instance'],
                    world_name=result['current_world'] or "不明",
                    user_count=len(result['users_in_instance']),
                    users=result['users_in_instance']
                )

        # 現在の状態を記録
        last_instance_id = result['current_instance']
        last_users = result['users_in_instance'].copy()
        last_world_name = result['current_world']

        # アバター検出のユーザー数を更新
        if screenshot_capture:
            screenshot_capture.update_user_count(len(last_users))

        # ワールド情報をログに出力
        if result['current_world'] and result['current_instance']:
            logger.info(f"[WORLD] {result['current_world']} (Instance: {result['current_instance']})")

        # Audio録音開始（ワールドに入っている場合）
        if audio_recorder and config.get("audio", {}).get("enabled", False):
            if config.get("audio", {}).get("auto_start", False) and result['current_world']:
                world_id = result['current_world'] or "unknown"
                audio_recorder.start_recording(world_id=world_id, instance_id=result['current_instance'])

        # スクリーンショット撮影（VRChat起動時）
        if screenshot_capture and config.get("screenshot", {}).get("enabled", False):
            if config.get("screenshot", {}).get("on_vrchat_start", False):
                screenshot_path = screenshot_capture.capture_vrchat_window(prefix="vrchat", reason="start")
                # Discordに通知
                if screenshot_path and discord_webhook and config.get("screenshot", {}).get("notify_discord", True):
                    discord_webhook.send_screenshot_notification(
                        screenshot_path=str(screenshot_path),
                        world_name=result['current_world'] or "不明",
                        reason="manual"
                    )
                # 画像分析
                if screenshot_path and image_analyzer:
                    analyze_screenshot(screenshot_path, world_name=result['current_world'] or "不明")

            # 定期的な自動キャプチャを開始
            if config.get("screenshot", {}).get("auto_capture", False):
                interval = config.get("screenshot", {}).get("auto_capture_interval", 180)
                screenshot_capture.start_auto_capture(interval=interval)

            # アバター検出を開始
            avatar_detection_config = config.get("screenshot", {}).get("avatar_detection", {})
            if avatar_detection_config.get("enabled", False):
                detection_interval = avatar_detection_config.get("interval", 5)
                detection_sensitivity = avatar_detection_config.get("sensitivity", 0.10)
                detection_mode = avatar_detection_config.get("mode", "advanced")
                consecutive_frames = avatar_detection_config.get("consecutive_frames", 6)
                hold_seconds = avatar_detection_config.get("hold_seconds", 6.0)
                flow_min = avatar_detection_config.get("flow_min", 0.35)
                base_score_threshold = avatar_detection_config.get("base_score_threshold", 0.45)
                warmup_frames = avatar_detection_config.get("warmup_frames", 30)
                screenshot_capture.start_avatar_detection(
                    interval=detection_interval,
                    sensitivity=detection_sensitivity,
                    mode=detection_mode,
                    consecutive_frames=consecutive_frames,
                    hold_seconds=hold_seconds,
                    flow_min=flow_min,
                    base_score_threshold=base_score_threshold,
                    warmup_frames=warmup_frames
                )

    except Exception as e:
        print(f"[エラー] ログ監視の開始に失敗: {e}")


def update_log_monitoring():
    """
    ログ監視を更新（定期的に呼び出される）
    """
    global last_instance_id, last_users, last_world_name

    try:
        # ログディレクトリを取得
        log_dir = parse_logs.get_vrchat_log_directory()

        # 最新のログファイルを取得
        log_file = parse_logs.get_latest_log_file(log_dir)

        # ログを解析
        result = parse_logs.parse_vrchat_log(log_file, verbose=False)

        current_instance = result['current_instance']
        current_users = result['users_in_instance']
        current_world = result['current_world']

        # マイクデバイスの更新
        if audio_recorder and result.get('microphone_device'):
            if audio_recorder.mic_device != result['microphone_device']:
                audio_recorder.set_mic_device(result['microphone_device'])

        # ワールド変更を検出（インスタンス変更またはワールド名変更）
        world_changed = False
        if current_world and current_world != last_world_name and last_world_name is not None:
            world_changed = True
            print(f"\n[検出] ワールド変更: {current_world}")
            logger.info(f"[WORLD] {current_world} (Instance: {current_instance})")

        # インスタンス変更を検出
        if current_instance and current_instance != last_instance_id and last_instance_id is not None:
            print(f"\n[検出] インスタンス変更: {current_instance}")

            # Discord通知
            if discord_webhook and config.get("discord", {}).get("notifications", {}).get("instance_changed", False):
                discord_webhook.send_instance_changed(
                    old_instance=last_instance_id,
                    new_instance=current_instance,
                    world_name=current_world or "不明"
                )

            # スクリーンショット撮影（インスタンス変更時）
            if screenshot_capture and config.get("screenshot", {}).get("enabled", False):
                if config.get("screenshot", {}).get("on_instance_change", False):
                    screenshot_path = screenshot_capture.capture_on_instance_change(
                        instance_id=current_instance,
                        world_name=current_world or "不明"
                    )
                    # Discordに通知
                    if screenshot_path and discord_webhook:
                        discord_webhook.send_screenshot_notification(
                            screenshot_path=str(screenshot_path),
                            world_name=current_world or "不明",
                            reason="instance_change"
                        )
                    # 画像分析
                    if screenshot_path and image_analyzer:
                        analyze_screenshot(screenshot_path, world_name=current_world or "不明")

        # Audio録音の停止・開始（ワールド変更時）
        if audio_recorder and config.get("audio", {}).get("enabled", False) and world_changed:
            # 現在録音中なら停止
            if audio_recorder.is_recording:
                # 録音停止前にワールドIDとタイムスタンプを保存
                previous_world_id = audio_recorder.current_world_id
                previous_timestamp = audio_recorder.current_timestamp

                logger.info(f"ワールド変更検出: 録音を停止します")
                audio_recorder.stop_recording()

                # 音声分析を実行（ワールド変更時、録音停止直後）
                # 前回のワールドのファイルのみを分析
                if audio_analyzer and previous_world_id and previous_timestamp:
                    # ワールドIDをファイル名用にサニタイズ
                    safe_world_id = audio_recorder._sanitize_filename(previous_world_id)
                    logger.info(f"前回のワールド '{previous_world_id}' の音声を分析します")
                    analyze_audio_recordings(specific_world_id=safe_world_id, specific_timestamp=previous_timestamp)

            # 新しいワールドで録音開始
            if current_world:
                logger.info(f"新しいワールドで録音を開始します: {current_world}")
                audio_recorder.start_recording(world_id=current_world, instance_id=current_instance)

        # ユーザーの参加/退出を検出
        # 最初のログ監視開始時はlast_usersが空なので、通知を送らない
        if current_instance == last_instance_id and last_users:
            if discord_webhook:
                notifications = config.get("discord", {}).get("notifications", {})

                # 新規参加ユーザー
                if notifications.get("user_joined", False):
                    for user, user_id in current_users.items():
                        if user not in last_users:
                            print(f"\n[検出] ユーザー参加: {user}")
                            logger.info(f"[JOIN] {user} joined {current_world or '不明'}")
                            discord_webhook.send_user_joined(user, user_id, len(current_users))

                # 退出ユーザー
                if notifications.get("user_left", False):
                    for user, user_id in last_users.items():
                        if user not in current_users:
                            print(f"\n[検出] ユーザー退出: {user}")
                            logger.info(f"[LEFT] {user} left {current_world or '不明'}")
                            discord_webhook.send_user_left(user, user_id, len(current_users))

        # 状態を更新
        last_instance_id = current_instance
        last_users = current_users.copy()
        last_world_name = current_world

        # アバター検出のユーザー数を更新
        if screenshot_capture:
            screenshot_capture.update_user_count(len(last_users))

        # 録音の自動分割チェック
        if audio_recorder and audio_recorder.is_recording:
            if audio_recorder._should_split_recording():
                logger.info("録音時間が分割間隔に達しました。自動分割を実行します...")
                audio_recorder._split_recording_internal()

        # 簡易的な表示
        print(f"\r[更新] インスタンス: {current_instance or '不明'} | ユーザー数: {len(current_users)}人", end="", flush=True)

    except Exception as e:
        print(f"\n[エラー] ログ更新中にエラー: {e}")


def analyze_screenshot(screenshot_path: Path, world_name: str = "不明"):
    """
    スクリーンショットを画像分析して結果をDiscordに通知
    Args:
        screenshot_path: スクリーンショットのパス
        world_name: ワールド名
    """
    if not image_analyzer:
        return

    ai_config = config.get("ai", {})
    image_config = ai_config.get("image_analysis", {})

    if not image_config.get("analyze_screenshots", True):
        return

    try:
        logger.info(f"画像分析を開始: {screenshot_path.name}")
        result = image_analyzer.analyze_avatar_presence(screenshot_path)

        logger.info(f"画像分析結果: has_other_avatars={result['has_other_avatars']}, "
                   f"avatar_count={result['avatar_count']}, confidence={result['confidence']}")

        # Discord通知
        if discord_webhook:
            discord_webhook.send_avatar_detection(
                screenshot_path=str(screenshot_path),
                has_avatars=result['has_other_avatars'],
                avatar_count=result['avatar_count'],
                confidence=result['confidence'],
                description=result['description'],
                world_name=world_name
            )

    except Exception as e:
        logger.error(f"画像分析中にエラー: {e}")
        import traceback
        traceback.print_exc()


def analyze_audio_recordings(specific_world_id: Optional[str] = None, specific_timestamp: Optional[str] = None):
    """
    録音された音声ファイルを分析

    Args:
        specific_world_id: 特定のワールドIDのファイルのみ分析（Noneの場合は全て）
        specific_timestamp: 特定のタイムスタンプのファイルのみ分析（Noneの場合は全て）
    """
    if not audio_analyzer:
        return

    ai_config = config.get("ai", {})
    audio_config = ai_config.get("audio_analysis", {})

    if not audio_config.get("analyze_on_upload", False):
        logger.info("音声分析がスキップされました（analyze_on_uploadが無効）")
        return

    try:
        audio_dir = audio_recorder.audio_dir if audio_recorder else Path("logs/audio")
        if not audio_dir.exists():
            logger.warning(f"音声ディレクトリが見つかりません: {audio_dir}")
            return

        logger.info("音声ファイルの分析を開始します...")
        if specific_world_id or specific_timestamp:
            logger.info(f"  フィルタ: world_id={specific_world_id}, timestamp={specific_timestamp}")
        print("\n[AI音声分析] 録音された音声ファイルを分析中...")

        # ファイルリストを取得
        audio_paths = list(audio_dir.glob("*.m4a"))
        if not audio_paths:
            logger.info("分析対象の音声ファイルがありませんでした")
            print("[AI音声分析] 分析対象のファイルがありませんでした")
            return

        logger.info(f"Found {len(audio_paths)} audio files in {audio_dir}")

        # 分割ファイルをグループ化
        groups = audio_analyzer.group_split_files(audio_paths)
        logger.info(f"Grouped into {len(groups)} recording sessions")

        # フィルタリング（処理前に実行）
        if specific_world_id or specific_timestamp:
            logger.info(f"音声分析フィルタ: world_id={specific_world_id}, timestamp={specific_timestamp}")
            filtered_groups = {}
            for group_name, files in groups.items():
                # グループ名パターン: {world_id}-{timestamp}
                match_world = True
                match_timestamp = True

                if specific_world_id:
                    match_world = group_name.startswith(specific_world_id)
                    logger.debug(f"  {group_name}: world_id match={match_world} (looking for '{specific_world_id}')")

                if specific_timestamp:
                    match_timestamp = specific_timestamp in group_name
                    logger.debug(f"  {group_name}: timestamp match={match_timestamp} (looking for '{specific_timestamp}')")

                if match_world and match_timestamp:
                    filtered_groups[group_name] = files
                    logger.info(f"  ✓ {group_name}: フィルタを通過")
                else:
                    logger.info(f"  ✗ {group_name}: フィルタでスキップ")

            groups = filtered_groups
            logger.info(f"フィルタ後: {len(groups)}個のセッション")

        if not groups:
            logger.info("フィルタ後、分析対象のファイルがありませんでした")
            return

        # 音声分析処理を別スレッドで実行する関数
        def process_audio_analysis():
            try:
                # フィルタリング済みのグループのみを処理
                results = {}
                for group_name, files in groups.items():
                    logger.info(f"Processing group '{group_name}' with {len(files)} parts")
                    results[group_name] = audio_analyzer.process_split_audio_group(files)

                if not results:
                    logger.info("フィルタ後、分析対象のファイルがありませんでした")
                    return

                logger.info(f"音声分析が完了しました: {len(results)}個のセッション")
                print(f"[AI音声分析] {len(results)}個のセッションを分析しました")

                # 結果をログに出力
                for group_name, result in results.items():
                    if result.get('skipped'):
                        logger.info(f"[{group_name}] スキップ: {result.get('skip_reason')}")
                        logger.info(f"  → AI分析をスキップしてコストを節約しました")
                        continue

                    if result.get('error'):
                        logger.error(f"[{group_name}] エラー: {result.get('error')}")
                        continue

                    logger.info(f"[{group_name}] 分析完了 ({result.get('total_parts', 1)} parts)")
                    logger.info(f"  トピック: {', '.join(result.get('topics', []))}")
                    logger.info(f"  概要: {result.get('summary', '')}")

                    if result.get('decisions'):
                        logger.info(f"  決めたこと: {', '.join(result['decisions'])}")
                    if result.get('promises'):
                        logger.info(f"  約束したこと: {', '.join(result['promises'])}")

                # Discord通知（オプション）
                if discord_webhook and audio_config.get("notify_discord", False):
                    for group_name, result in results.items():
                        # group_nameからワールド名を抽出（例: "wrld_xxx-20250113_041049"）
                        world_name = group_name.split('-')[0] if '-' in group_name else group_name

                        try:
                            # スキップされた場合は会話なし通知
                            if result.get('skipped'):
                                skip_reason = result.get('skip_reason', '不明な理由')
                                discord_webhook.send_no_conversation(
                                    world_name=world_name,
                                    reason=skip_reason
                                )
                                logger.info(f"[{group_name}] Discord通知を送信しました（会話なし）")
                                continue

                            # エラーの場合はスキップ
                            if result.get('error'):
                                continue

                            # 音声分析結果をDiscordに送信
                            discord_webhook.send_conversation_summary(
                                world_name=world_name,
                                topics=result.get('topics', []),
                                summary=result.get('summary', ''),
                                decisions=result.get('decisions'),
                                promises=result.get('promises'),
                                duration_minutes=None  # 録音時間は今後実装可能
                            )
                            logger.info(f"[{group_name}] Discord通知を送信しました（会話サマリ）")
                        except Exception as e:
                            logger.error(f"[{group_name}] Discord通知の送信に失敗: {e}")

            except Exception as e:
                logger.error(f"音声分析スレッド内でエラー: {e}")
                import traceback
                traceback.print_exc()

        # 別スレッドで処理を開始
        analysis_thread = threading.Thread(
            target=process_audio_analysis,
            daemon=True,
            name=f"AudioAnalysis-{specific_world_id or 'all'}-{specific_timestamp or 'all'}"
        )
        analysis_thread.start()
        logger.info(f"音声分析を別スレッドで開始しました: {len(groups)}個のセッション (world_id={specific_world_id}, timestamp={specific_timestamp})")
        print(f"[AI音声分析] バックグラウンドで{len(groups)}個のセッションを分析中...")

    except Exception as e:
        logger.error(f"音声分析中にエラー: {e}")
        import traceback
        traceback.print_exc()


def stop_log_monitoring():
    """
    ログ監視を停止
    """
    # Audio録音を停止（停止前にワールド情報を保存）
    previous_world_id = None
    previous_timestamp = None

    if audio_recorder and audio_recorder.is_recording:
        # 録音停止前にワールドIDとタイムスタンプを保存
        previous_world_id = audio_recorder.current_world_id
        previous_timestamp = audio_recorder.current_timestamp

        if config.get("audio", {}).get("auto_stop", True):
            audio_recorder.stop_recording()

    # 音声分析を実行（最後のワールドのみ）
    if audio_analyzer and previous_world_id and previous_timestamp:
        safe_world_id = audio_recorder._sanitize_filename(previous_world_id)
        logger.info(f"最後のワールド '{previous_world_id}' の音声を分析します")
        analyze_audio_recordings(specific_world_id=safe_world_id, specific_timestamp=previous_timestamp)

    # スクリーンショット自動キャプチャを停止
    if screenshot_capture and screenshot_capture.is_auto_capture_running:
        screenshot_capture.stop_auto_capture()

    # アバター検出を停止
    if screenshot_capture and screenshot_capture.is_avatar_detection_running:
        screenshot_capture.stop_avatar_detection()

    print("[動作停止] VRChatログの監視を停止しました")


def upload_files_to_cloud():
    """
    ファイルをクラウドにアップロード
    """
    global last_upload_date

    if not file_uploader:
        logger.warning("File uploader is not initialized")
        return

    upload_config = config.get("upload", {})
    if not upload_config.get("enabled", False):
        logger.info("File upload is disabled")
        return

    logger.info("Starting file upload process...")
    print("\n[アップロード] ファイルをtmpfiles.orgにアップロード中...")
    print("[注意] アップロードされたファイルは60分後に自動削除されます")

    # アップロード処理
    cleanup = upload_config.get("cleanup_after_upload", True)

    upload_results, password = file_uploader.process_and_upload_all(cleanup=cleanup)

    if upload_results:
        logger.info(f"Successfully uploaded {len(upload_results)} files")
        print(f"[完了] {len(upload_results)}個のファイルをアップロードしました")
        print(f"[パスワード] ZIP解凍パスワード: {password}")

        # Discord通知
        if discord_webhook and upload_config.get("notify_discord", True):
            discord_webhook.send_file_upload_complete(upload_results, password)

        # 最後のアップロード日を記録
        last_upload_date = datetime.now().strftime("%Y%m%d")
    else:
        logger.info("No files to upload or upload failed")
        print("[情報] アップロードするファイルがありませんでした")


def main():
    """メイン処理"""
    global discord_webhook, screenshot_capture, audio_recorder, file_uploader, image_analyzer, audio_analyzer, config

    # コマンドライン引数のパース
    parser = argparse.ArgumentParser(description='VRChat Sugar Checker - VRChat.exeプロセス監視ツール')
    parser.add_argument('--config', type=str, default='config.json', help='設定ファイルのパス')
    parser.add_argument('--interval', type=int, help='プロセスチェック間隔（秒）')
    args = parser.parse_args()

    # ログディレクトリのパス
    logs_dir = Path(__file__).parent.parent / "logs"

    # ログ設定のセットアップ
    setup_logging(logs_dir)

    # 古いログファイルのクリーンアップ
    cleanup_old_logs(logs_dir, days=7)

    # 設定ファイルのパスを絶対パスに変換
    config_path = Path(__file__).parent / args.config

    # 設定を読み込む
    config = load_config(config_path)

    # Discord WebHookの初期化
    discord_config = config.get("discord", {})
    if discord_config.get("enabled", False):
        webhook_url = discord_config.get("webhook_url", "")
        if webhook_url:
            discord_webhook = DiscordWebhook(
                webhook_url=webhook_url,
                username=discord_config.get("username", "VRChat Sugar Checker"),
                avatar_url=discord_config.get("avatar_url", "")
            )
            logger.info("Discord通知が有効になっています")
        else:
            logger.warning("Discord通知が有効ですが、webhook_urlが設定されていません")
    else:
        logger.info("Discord通知は無効です")

    # Audio録音の初期化
    audio_config = config.get("audio", {})
    if audio_config.get("enabled", False):
        # デバッグ設定を取得
        keep_source_files = audio_config.get("debug", {}).get("keep_source_files", False)
        split_interval_seconds = audio_config.get("split_interval_seconds", 3600)
        audio_recorder = AudioRecorder(
            logs_dir,
            keep_source_files=keep_source_files,
            split_interval_seconds=split_interval_seconds
        )
        logger.info("Audio録音が有効になっています")
        logger.info(f"録音分割間隔: {split_interval_seconds}秒 ({split_interval_seconds/3600:.1f}時間)")
        if keep_source_files:
            logger.info("デバッグモード: wavファイルを保持します")

        # 古い音声ファイルのクリーンアップ
        retention_days = audio_config.get("retention_days", 7)
        audio_recorder.cleanup_old_audio_files(days=retention_days)
    else:
        logger.info("Audio録音は無効です")

    # スクリーンショットキャプチャの初期化
    screenshot_config = config.get("screenshot", {})
    if screenshot_config.get("enabled", False):
        # Discord通知コールバックを定義（reason別に通知を制御）
        def screenshot_callback(screenshot_path: Path, reason: str):
            """スクリーンショット撮影時のDiscord通知と画像分析コールバック"""
            # Discord通知（reason別に設定を確認）
            should_notify = False
            if discord_webhook:
                if reason == "auto_capture":
                    # auto_capture用の設定を確認
                    should_notify = screenshot_config.get("notify_discord", False)
                elif reason == "avatar_detected":
                    # avatar_detection用の設定を確認
                    avatar_detection_config = screenshot_config.get("avatar_detection", {})
                    should_notify = avatar_detection_config.get("notify_discord", True)
                else:
                    # その他（手動、インスタンス変更など）は従来通り
                    should_notify = screenshot_config.get("notify_discord", True)

                if should_notify:
                    discord_webhook.send_screenshot_notification(
                        screenshot_path=str(screenshot_path),
                        world_name=last_world_name or "不明",
                        reason=reason
                    )

            # 画像分析（自動キャプチャまたはアバター検出の場合）
            if reason in ["auto_capture", "avatar_detected"] and image_analyzer:
                analyze_screenshot(screenshot_path, world_name=last_world_name or "不明")

        screenshot_capture = ScreenshotCapture(logs_dir, screenshot_callback=screenshot_callback)
        logger.info("スクリーンショット撮影が有効になっています")

        # 古いスクリーンショットのクリーンアップ
        retention_days = screenshot_config.get("retention_days", 7)
        screenshot_capture.cleanup_old_screenshots(days=retention_days)
    else:
        logger.info("スクリーンショット撮影は無効です")

    # ファイルアップローダーの初期化
    upload_config = config.get("upload", {})
    if upload_config.get("enabled", False):
        file_uploader = FileUploader(logs_dir)
        logger.info("ファイルアップロードが有効になっています")

        # 古いエラーレスポンスファイルのクリーンアップ
        file_uploader.cleanup_old_error_files(days=7)
    else:
        logger.info("ファイルアップロードは無効です")

    # AI画像分析の初期化
    ai_config = config.get("ai", {})
    if ai_config.get("enabled", False) and IMAGE_ANALYZER_AVAILABLE:
        image_config = ai_config.get("image_analysis", {})
        if image_config.get("enabled", False):
            api_key = ai_config.get("openai_api_key", "")
            if api_key and api_key != "YOUR_OPENAI_API_KEY":
                try:
                    model = image_config.get("model", "gpt-4o")
                    image_analyzer = ImageAnalyzer(api_key=api_key, model=model)
                    logger.info(f"AI画像分析が有効になっています (model: {model})")
                except Exception as e:
                    logger.error(f"ImageAnalyzer初期化エラー: {e}")
            else:
                logger.warning("AI画像分析が有効ですが、OpenAI APIキーが設定されていません")
        else:
            logger.info("AI画像分析は無効です")
    else:
        if not IMAGE_ANALYZER_AVAILABLE:
            logger.info("AI画像分析モジュールが利用できません")
        else:
            logger.info("AI機能は無効です")

    # AI音声分析の初期化
    if ai_config.get("enabled", False) and AUDIO_ANALYZER_AVAILABLE:
        audio_config = ai_config.get("audio_analysis", {})
        if audio_config.get("enabled", False):
            api_key = ai_config.get("openai_api_key", "")
            if api_key and api_key != "YOUR_OPENAI_API_KEY":
                try:
                    transcription_model = audio_config.get("transcription_model", "whisper-1")
                    analysis_model = audio_config.get("analysis_model", "gpt-4o")
                    preprocessing_config = audio_config.get("preprocessing", {})
                    enable_preprocessing = preprocessing_config.get("enabled", True)

                    audio_analyzer = AudioAnalyzer(
                        api_key=api_key,
                        transcription_model=transcription_model,
                        analysis_model=analysis_model,
                        enable_preprocessing=enable_preprocessing
                    )
                    logger.info(f"AI音声分析が有効になっています (transcription: {transcription_model}, analysis: {analysis_model}, preprocessing: {enable_preprocessing})")
                except Exception as e:
                    logger.error(f"AudioAnalyzer初期化エラー: {e}")
            else:
                logger.warning("AI音声分析が有効ですが、OpenAI APIキーが設定されていません")
        else:
            logger.info("AI音声分析は無効です")
    else:
        if not AUDIO_ANALYZER_AVAILABLE:
            logger.info("AI音声分析モジュールが利用できません")
        else:
            logger.info("AI機能は無効です（音声分析）")

    # プロセスチェック間隔
    check_interval = args.interval if args.interval else config.get("monitoring", {}).get("check_interval", 5)

    # プロセス監視を開始
    monitor_vrchat_process(check_interval=check_interval)


if __name__ == "__main__":
    main()
