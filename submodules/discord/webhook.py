#!/usr/bin/env python3
"""
Discord WebHook通知モジュール
VRChatのイベント（起動/終了、ユーザー参加/退出など）をDiscordに通知します
"""
import requests
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class DiscordWebhook:
    """Discord WebHook送信クラス"""

    def __init__(self, webhook_url: str, username: str = "VRChat Sugar Checker", avatar_url: Optional[str] = None):
        """
        初期化
        Args:
            webhook_url: Discord WebHookのURL
            username: Botの表示名
            avatar_url: Botのアバター画像URL
        """
        self.webhook_url = webhook_url
        self.username = username
        self.avatar_url = avatar_url

    def send(self, content: str = None, embed: Dict = None, embeds: List[Dict] = None) -> bool:
        """
        WebHookを送信
        Args:
            content: メッセージ本文
            embed: 埋め込み（単一）
            embeds: 埋め込み（複数）
        Returns:
            bool: 送信成功ならTrue
        """
        try:
            payload = {
                "username": self.username,
            }

            if self.avatar_url:
                payload["avatar_url"] = self.avatar_url

            if content:
                payload["content"] = content

            if embed:
                payload["embeds"] = [embed]
            elif embeds:
                payload["embeds"] = embeds

            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )

            if response.status_code == 204:
                logger.debug("Discord通知を送信しました")
                return True
            else:
                logger.error(f"Discord通知の送信に失敗: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Discord通知の送信中にエラーが発生: {e}")
            return False

    def send_vrchat_started(self) -> bool:
        """
        VRChat起動通知を送信
        Returns:
            bool: 送信成功ならTrue
        """
        embed = {
            "title": "🎮 VRChat起動",
            "description": "VRChat.exeが起動しました",
            "color": 0x00ff00,  # 緑色
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "VRChat Sugar Checker"
            }
        }
        return self.send(embed=embed)

    def send_vrchat_stopped(self) -> bool:
        """
        VRChat終了通知を送信
        Returns:
            bool: 送信成功ならTrue
        """
        embed = {
            "title": "🛑 VRChat終了",
            "description": "VRChat.exeが終了しました",
            "color": 0xff0000,  # 赤色
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "VRChat Sugar Checker"
            }
        }
        return self.send(embed=embed)

    def send_instance_info(self, instance_id: str, world_name: str, user_count: int, users: Dict[str, str]) -> bool:
        """
        インスタンス情報通知を送信
        Args:
            instance_id: インスタンスID
            world_name: ワールド名
            user_count: ユーザー数
            users: ユーザー辞書 {display_name: user_id}
        Returns:
            bool: 送信成功ならTrue
        """
        # ユーザーリストを整形
        user_list = []
        for i, (display_name, user_id) in enumerate(sorted(users.items()), 1):
            user_list.append(f"{i}. {display_name}")
            # 最大20人まで表示
            if i >= 20:
                remaining = len(users) - 20
                if remaining > 0:
                    user_list.append(f"... 他{remaining}人")
                break

        fields = [
            {
                "name": "🌍 ワールド",
                "value": world_name or "不明",
                "inline": False
            },
            {
                "name": "📍 インスタンスID",
                "value": f"```{instance_id or '不明'}```",
                "inline": False
            },
            {
                "name": f"👥 一緒にいるユーザー ({user_count}人)",
                "value": "\n".join(user_list) if user_list else "なし",
                "inline": False
            }
        ]

        embed = {
            "title": "📊 インスタンス情報",
            "color": 0x3498db,  # 青色
            "fields": fields,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "VRChat Sugar Checker"
            }
        }
        return self.send(embed=embed)

    def send_user_joined(self, display_name: str, user_id: str, user_count: int) -> bool:
        """
        ユーザー参加通知を送信
        Args:
            display_name: 表示名
            user_id: ユーザーID
            user_count: 現在のユーザー数
        Returns:
            bool: 送信成功ならTrue
        """
        embed = {
            "title": "✅ ユーザー参加",
            "description": f"**{display_name}** が参加しました",
            "color": 0x2ecc71,  # 緑色
            "fields": [
                {
                    "name": "ユーザーID",
                    "value": f"`{user_id}`",
                    "inline": False
                },
                {
                    "name": "現在のユーザー数",
                    "value": f"{user_count}人",
                    "inline": True
                }
            ],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "VRChat Sugar Checker"
            }
        }
        return self.send(embed=embed)

    def send_user_left(self, display_name: str, user_id: str, user_count: int) -> bool:
        """
        ユーザー退出通知を送信
        Args:
            display_name: 表示名
            user_id: ユーザーID
            user_count: 現在のユーザー数
        Returns:
            bool: 送信成功ならTrue
        """
        embed = {
            "title": "❌ ユーザー退出",
            "description": f"**{display_name}** が退出しました",
            "color": 0xe74c3c,  # 赤色
            "fields": [
                {
                    "name": "ユーザーID",
                    "value": f"`{user_id}`",
                    "inline": False
                },
                {
                    "name": "現在のユーザー数",
                    "value": f"{user_count}人",
                    "inline": True
                }
            ],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "VRChat Sugar Checker"
            }
        }
        return self.send(embed=embed)

    def send_instance_changed(self, old_instance: str, new_instance: str, world_name: str) -> bool:
        """
        インスタンス変更通知を送信
        Args:
            old_instance: 前のインスタンスID
            new_instance: 新しいインスタンスID
            world_name: ワールド名
        Returns:
            bool: 送信成功ならTrue
        """
        embed = {
            "title": "🔄 インスタンス変更",
            "description": f"新しいインスタンスに移動しました",
            "color": 0xf39c12,  # オレンジ色
            "fields": [
                {
                    "name": "🌍 ワールド",
                    "value": world_name or "不明",
                    "inline": False
                },
                {
                    "name": "📍 新しいインスタンス",
                    "value": f"```{new_instance or '不明'}```",
                    "inline": False
                }
            ],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "VRChat Sugar Checker"
            }
        }
        return self.send(embed=embed)


def send_notification(webhook_url: str, message: str, title: str = None, color: int = 0x3498db) -> bool:
    """
    シンプルな通知を送信（便利関数）
    Args:
        webhook_url: Discord WebHookのURL
        message: メッセージ
        title: タイトル（オプション）
        color: 埋め込みの色（デフォルト: 青）
    Returns:
        bool: 送信成功ならTrue
    """
    webhook = DiscordWebhook(webhook_url)

    if title:
        embed = {
            "title": title,
            "description": message,
            "color": color,
            "timestamp": datetime.utcnow().isoformat()
        }
        return webhook.send(embed=embed)
    else:
        return webhook.send(content=message)
