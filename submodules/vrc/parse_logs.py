#!/usr/bin/env python3
"""
VRChatログファイル解析スクリプト
ローカルログファイルから現在のインスタンスにいるユーザーを抽出します
"""
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set
import glob


def get_vrchat_log_directory():
    """
    VRChatのログディレクトリパスを取得
    Returns:
        Path: ログディレクトリのパス
    """
    # WSL環境かどうかチェック
    if 'microsoft' in os.uname().release.lower():
        # WSLの場合、/mnt/c/Users/... の形式を試す
        username = os.getenv('USER')
        # Windows側のユーザー名を取得（環境変数から）
        windows_username = os.getenv('WINDOWS_USER') or username
        vrchat_log_dir = Path(f"/mnt/c/Users/{windows_username}/AppData/LocalLow/VRChat/VRChat")

        if not vrchat_log_dir.exists():
            # 別の可能性を試す
            print(f"[INFO] {vrchat_log_dir} が見つかりません")
            print(f"[INFO] WINDOWS_USER環境変数を設定してください:")
            print(f"       export WINDOWS_USER=YourWindowsUsername")
            raise FileNotFoundError(f"VRChatログディレクトリが見つかりません: {vrchat_log_dir}")
    else:
        # Windowsの場合
        vrchat_log_dir = Path.home() / "AppData" / "LocalLow" / "VRChat" / "VRChat"

        if not vrchat_log_dir.exists():
            raise FileNotFoundError(f"VRChatログディレクトリが見つかりません: {vrchat_log_dir}")

    return vrchat_log_dir


def get_latest_log_file(log_dir: Path) -> Path:
    """
    最新のログファイルを取得
    Args:
        log_dir: ログディレクトリ
    Returns:
        Path: 最新のログファイルのパス
    """
    # output_log_*.txt のパターンでファイルを検索
    log_files = list(log_dir.glob("output_log_*.txt"))

    if not log_files:
        raise FileNotFoundError(f"ログファイルが見つかりません: {log_dir}")

    # 最新のファイルを取得（更新日時順）
    latest_log = max(log_files, key=lambda p: p.stat().st_mtime)

    return latest_log


def parse_vrchat_log(log_file: Path, verbose: bool = False) -> Dict:
    """
    VRChatログファイルを解析
    Args:
        log_file: ログファイルのパス
        verbose: 詳細ログを表示するか
    Returns:
        Dict: 解析結果
    """
    print(f"[INFO] ログファイルを解析中: {log_file.name}")
    print(f"[INFO] ファイルサイズ: {log_file.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"[INFO] 最新のインスタンス情報を取得しています...")

    # 現在のインスタンス情報
    current_instance = None
    current_world = None

    # インスタンスにいるユーザー（join/leaveを追跡）
    users_in_instance = {}  # {display_name: user_id}

    # join/leave履歴
    join_events = []
    leave_events = []

    # 正規表現パターン
    # [Behaviour] Entering Room: worldName
    entering_room_pattern = re.compile(r'\[Behaviour\] Entering Room: (.+)')

    # [Behaviour] Joining wrld_xxx:instance~region(jp)
    joining_pattern = re.compile(r'\[Behaviour\] Joining (.+)')

    # OnPlayerJoined DisplayName (usr_xxx)
    # インスタンスに参加した人（既にいた人も含む）
    player_joined_pattern = re.compile(r'OnPlayerJoined (.+?) \((usr_[a-f0-9\-]+)\)')

    # OnPlayerLeft DisplayName (usr_xxx)
    # 退出した人
    player_left_pattern = re.compile(r'OnPlayerLeft (.+?) \((usr_[a-f0-9\-]+)\)')

    # ログの時刻を解析するパターン
    # 2025.11.09 02:32:03 Log        -  ...
    timestamp_pattern = re.compile(r'^(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})')

    # ログファイルを読み込み
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()

            # 時刻を抽出
            timestamp_str = None
            timestamp_match = timestamp_pattern.match(line)
            if timestamp_match:
                timestamp_str = timestamp_match.group(1)
                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y.%m.%d %H:%M:%S')
                except:
                    timestamp = None
            else:
                timestamp = None

            # Joining インスタンス検出
            match = joining_pattern.search(line)
            if match:
                instance_location = match.group(1)

                # 新しいインスタンスに入った場合、ユーザーリストをリセット
                if current_instance != instance_location:
                    current_instance = instance_location
                    users_in_instance.clear()
                    join_events.clear()
                    leave_events.clear()
                    if verbose:
                        time_str = f" [{timestamp_str}]" if timestamp_str else ""
                        print(f"\n[INFO]{time_str} インスタンス変更を検出: {instance_location}")
                        print(f"[INFO] ユーザーリストをリセット")

            # Entering Room 検出
            match = entering_room_pattern.search(line)
            if match:
                current_world = match.group(1)
                if verbose:
                    time_str = f" [{timestamp_str}]" if timestamp_str else ""
                    print(f"[INFO]{time_str} ワールド名: {current_world}")

            # OnPlayerJoined: 参加した人（既にいた人も含む）
            match = player_joined_pattern.search(line)
            if match:
                display_name = match.group(1).strip()
                user_id = match.group(2).strip()
                users_in_instance[display_name] = user_id
                join_events.append({
                    'time': timestamp,
                    'time_str': timestamp_str,
                    'user': display_name,
                    'user_id': user_id,
                    'event': 'join'
                })
                if verbose:
                    time_str = f"[{timestamp_str}]" if timestamp_str else ""
                    print(f"  {time_str} [JOIN] {display_name} ({user_id})")

            # OnPlayerLeft: 退出した人
            match = player_left_pattern.search(line)
            if match:
                display_name = match.group(1).strip()
                user_id = match.group(2).strip()
                users_in_instance.pop(display_name, None)
                leave_events.append({
                    'time': timestamp,
                    'time_str': timestamp_str,
                    'user': display_name,
                    'user_id': user_id,
                    'event': 'leave'
                })
                if verbose:
                    time_str = f"[{timestamp_str}]" if timestamp_str else ""
                    print(f"  {time_str} [LEFT] {display_name} ({user_id})")

    return {
        'current_instance': current_instance,
        'current_world': current_world,
        'users_in_instance': users_in_instance,
        'join_events': join_events,
        'leave_events': leave_events
    }


def display_results(result: Dict):
    """
    解析結果を表示
    Args:
        result: 解析結果
    """
    print("\n" + "="*60)
    print("最新のインスタンス情報")
    print("="*60)

    if result['current_instance']:
        print(f"インスタンスID: {result['current_instance']}")
    else:
        print("インスタンス情報: （検出できませんでした）")

    if result['current_world']:
        print(f"ワールド名: {result['current_world']}")

    # JOIN/LEAVEイベントログを表示
    print("\n" + "="*60)
    print("JOIN/LEAVEイベントログ")
    print("="*60)

    all_events = []
    for event in result['join_events']:
        all_events.append(('JOIN', event))
    for event in result['leave_events']:
        all_events.append(('LEAVE', event))

    # 時刻順にソート
    all_events.sort(key=lambda x: x[1].get('time_str', ''))

    if all_events:
        for event_type, event in all_events:
            time_str = event.get('time_str', '不明')
            user = event.get('user', '不明')
            user_id = event.get('user_id', '不明')
            print(f"  [{time_str}] [{event_type}] {user} ({user_id})")
    else:
        print("  （イベントなし）")

    # 現在一緒にいるユーザー
    users = result['users_in_instance']
    print("\n" + "="*60)
    print(f"現在一緒にいるユーザー ({len(users)}人)")
    print("="*60)

    if users:
        for i, (user, user_id) in enumerate(sorted(users.items()), 1):
            print(f"  {i}. {user}")
            print(f"     ID: {user_id}")
    else:
        print("  ⚠️ 現在インスタンスにいるユーザーは検出されませんでした")
        print("  （まだ誰も join していないか、ログが古い可能性があります）")

    print("\n" + "="*60)


def main():
    """メイン処理"""
    try:
        print("VRChatログファイル解析スクリプト")
        print("="*60)

        # ログディレクトリを取得
        log_dir = get_vrchat_log_directory()
        print(f"[INFO] ログディレクトリ: {log_dir}")

        # 最新のログファイルを取得
        log_file = get_latest_log_file(log_dir)
        print(f"[INFO] 最新のログファイル: {log_file.name}")
        print(f"[INFO] 最終更新: {datetime.fromtimestamp(log_file.stat().st_mtime)}")

        # ログファイルを解析
        result = parse_vrchat_log(log_file)

        # 結果を表示
        display_results(result)

        print("\n✅ 処理が完了しました！")

    except FileNotFoundError as e:
        print(f"\n❌ エラー: {e}")
        print("\nVRChatがインストールされているか、ログファイルが存在するか確認してください。")
        print(f"ログディレクトリ: {Path.home() / 'AppData' / 'LocalLow' / 'VRChat' / 'VRChat'}")
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()