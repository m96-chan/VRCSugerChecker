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
from pathlib import Path
from datetime import datetime

# submodulesのparse_logs.pyをインポート
sys.path.insert(0, str(Path(__file__).parent / "submodules" / "vrc"))
import parse_logs

# ロガー設定
logger = logging.getLogger(__name__)


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
        print(f"[エラー] プロセスチェック中にエラーが発生: {e}")
        return False


def monitor_vrchat_process(check_interval=5):
    """
    VRChat.exeのプロセスを監視し、起動/終了に応じて処理を実行
    Args:
        check_interval: プロセスチェックの間隔（秒）
    """
    print("="*60)
    print("VRChat Sugar Checker 起動")
    print("="*60)
    print(f"VRChat.exeの起動を監視中... ({check_interval}秒間隔)")
    print("終了するには Ctrl+C を押してください\n")

    vrchat_was_running = False
    log_monitoring_active = False

    try:
        while True:
            vrchat_is_running = is_vrchat_running()

            # VRChatが起動した場合
            if vrchat_is_running and not vrchat_was_running:
                print("\n" + "="*60)
                print("[検出] VRChat.exe が起動しました！")
                print("="*60)
                log_monitoring_active = True
                start_log_monitoring()

            # VRChatが終了した場合
            elif not vrchat_is_running and vrchat_was_running:
                print("\n" + "="*60)
                print("[検出] VRChat.exe が終了しました")
                print("="*60)
                log_monitoring_active = False
                stop_log_monitoring()
                print(f"\nVRChat.exeの起動を監視中... ({check_interval}秒間隔)")

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

    except Exception as e:
        print(f"[エラー] ログ監視の開始に失敗: {e}")


def update_log_monitoring():
    """
    ログ監視を更新（定期的に呼び出される）
    """
    try:
        # ログディレクトリを取得
        log_dir = parse_logs.get_vrchat_log_directory()

        # 最新のログファイルを取得
        log_file = parse_logs.get_latest_log_file(log_dir)

        # ログを解析
        result = parse_logs.parse_vrchat_log(log_file)

        # 簡易的な表示（必要に応じて調整）
        print(f"\r[更新] インスタンス: {result['current_instance'] or '不明'} | ユーザー数: {len(result['users_in_instance'])}人", end="", flush=True)

    except Exception as e:
        print(f"\n[エラー] ログ更新中にエラー: {e}")


def stop_log_monitoring():
    """
    ログ監視を停止
    """
    print("[動作停止] VRChatログの監視を停止しました")


def main():
    """メイン処理"""
    # プロセス監視を開始（5秒間隔でチェック）
    monitor_vrchat_process(check_interval=5)


if __name__ == "__main__":
    main()
