#!/usr/bin/env python3
"""
滞在時間追跡モジュール
インスタンス内でのユーザーとの滞在時間を記録する
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class TimeTracker:
    """滞在時間追跡クラス"""

    def __init__(self):
        """初期化"""
        self.instance_start_time: Optional[datetime] = None
        self.user_join_times: Dict[str, datetime] = {}  # {user_id: join_time}
        self.user_total_times: Dict[str, timedelta] = {}  # {user_id: total_duration}
        self.user_display_names: Dict[str, str] = {}  # {user_id: display_name}

    def start_instance(self):
        """インスタンス参加時の初期化"""
        self.instance_start_time = datetime.now()
        self.user_join_times = {}
        self.user_total_times = {}
        self.user_display_names = {}
        logger.info("Started tracking instance time")

    def user_joined(self, user_id: str, display_name: str):
        """
        ユーザーが参加した時の記録
        Args:
            user_id: ユーザーID
            display_name: 表示名
        """
        if user_id not in self.user_join_times:
            self.user_join_times[user_id] = datetime.now()
            self.user_display_names[user_id] = display_name
            if user_id not in self.user_total_times:
                self.user_total_times[user_id] = timedelta(0)
            logger.debug(f"User joined: {display_name} ({user_id})")

    def user_left(self, user_id: str, display_name: str):
        """
        ユーザーが退出した時の記録
        Args:
            user_id: ユーザーID
            display_name: 表示名
        """
        if user_id in self.user_join_times:
            duration = datetime.now() - self.user_join_times[user_id]
            if user_id in self.user_total_times:
                self.user_total_times[user_id] += duration
            else:
                self.user_total_times[user_id] = duration

            self.user_display_names[user_id] = display_name
            del self.user_join_times[user_id]
            logger.debug(f"User left: {display_name} ({user_id}), duration: {duration}")

    def update_users(self, current_users: Dict[str, str]):
        """
        現在のユーザーリストで状態を更新
        Args:
            current_users: 現在のユーザー辞書 {display_name: user_id}
        """
        current_user_ids = set(current_users.values())
        tracked_user_ids = set(self.user_join_times.keys())

        # 新規参加ユーザー
        for display_name, user_id in current_users.items():
            if user_id not in tracked_user_ids:
                self.user_joined(user_id, display_name)

        # 退出ユーザー
        for user_id in tracked_user_ids:
            if user_id not in current_user_ids:
                display_name = self.user_display_names.get(user_id, "Unknown")
                self.user_left(user_id, display_name)

    def get_total_duration(self) -> timedelta:
        """
        総滞在時間を取得
        Returns:
            timedelta: 総滞在時間
        """
        if not self.instance_start_time:
            return timedelta(0)
        return datetime.now() - self.instance_start_time

    def get_user_durations(self) -> Dict[str, timedelta]:
        """
        各ユーザーとの滞在時間を取得
        Returns:
            Dict[str, timedelta]: {display_name: duration}
        """
        # 現在参加中のユーザーの時間を計算
        current_durations = {}
        for user_id, join_time in self.user_join_times.items():
            current_duration = datetime.now() - join_time
            total = self.user_total_times.get(user_id, timedelta(0)) + current_duration
            display_name = self.user_display_names.get(user_id, "Unknown")
            current_durations[display_name] = total

        # 既に退出したユーザーの時間も追加
        for user_id, total_time in self.user_total_times.items():
            if user_id not in self.user_join_times:
                display_name = self.user_display_names.get(user_id, "Unknown")
                if display_name not in current_durations:
                    current_durations[display_name] = total_time

        return current_durations

    def format_duration(self, duration: timedelta) -> str:
        """
        timedelta を HH:MM:SS 形式にフォーマット
        Args:
            duration: 時間
        Returns:
            str: HH:MM:SS 形式の文字列
        """
        total_seconds = int(duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def get_summary(self) -> Dict[str, str]:
        """
        滞在時間のサマリを取得
        Returns:
            Dict: サマリ情報
                {
                    'total_duration': str,  # 総滞在時間（HH:MM:SS）
                    'user_durations': Dict[str, str]  # {display_name: HH:MM:SS}
                }
        """
        total_duration = self.get_total_duration()
        user_durations = self.get_user_durations()

        user_durations_formatted = {
            name: self.format_duration(duration)
            for name, duration in user_durations.items()
        }

        return {
            'total_duration': self.format_duration(total_duration),
            'user_durations': user_durations_formatted
        }

    def reset(self):
        """追跡データをリセット"""
        self.instance_start_time = None
        self.user_join_times = {}
        self.user_total_times = {}
        self.user_display_names = {}
        logger.info("Reset time tracking data")
