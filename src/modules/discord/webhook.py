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
from urllib.parse import quote

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
        # インスタンスリンクを生成
        instance_link = self._create_instance_link(instance_id) if instance_id else None

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
            }
        ]

        # インスタンスリンクを追加
        if instance_link:
            fields.append({
                "name": "🔗 インスタンスリンク",
                "value": f"[VRChatで開く]({instance_link})",
                "inline": False
            })

        # ユーザーリストを整形（リンク付き）
        # Discord fieldのvalue制限: 1024文字
        # 複数のfieldに分割して表示
        sorted_users = sorted(users.items())
        user_fields = self._create_user_fields(sorted_users, user_count)
        fields.extend(user_fields)

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

    def _create_user_fields(self, sorted_users: list, user_count: int) -> list:
        """
        ユーザーリストをDiscord fieldの制限に合わせて分割
        Args:
            sorted_users: ソート済みユーザーリスト [(display_name, user_id), ...]
            user_count: 総ユーザー数
        Returns:
            list: Discord fields のリスト
        """
        fields = []
        current_field_lines = []
        current_field_length = 0
        field_num = 1
        user_index = 1

        # Discord fieldのvalue制限: 1024文字
        # 余裕を持って900文字で区切る
        MAX_FIELD_LENGTH = 900

        for display_name, user_id in sorted_users:
            # VRChatプロフィールリンクを作成
            profile_url = f"https://vrchat.com/home/user/{user_id}"
            line = f"{user_index}. [{display_name}]({profile_url})"
            line_length = len(line) + 1  # +1 for newline

            # 現在のfieldに追加すると制限を超える場合
            if current_field_length + line_length > MAX_FIELD_LENGTH and current_field_lines:
                # 現在のfieldを保存
                field_title = f"👥 一緒にいるユーザー ({user_count}人)" if field_num == 1 else f"👥 一緒にいるユーザー (続き {field_num})"
                fields.append({
                    "name": field_title,
                    "value": "\n".join(current_field_lines),
                    "inline": False
                })

                # 新しいfieldを開始
                current_field_lines = []
                current_field_length = 0
                field_num += 1

            # 行を追加
            current_field_lines.append(line)
            current_field_length += line_length
            user_index += 1

        # 最後のfieldを追加
        if current_field_lines:
            field_title = f"👥 一緒にいるユーザー ({user_count}人)" if field_num == 1 else f"👥 一緒にいるユーザー (続き {field_num})"
            fields.append({
                "name": field_title,
                "value": "\n".join(current_field_lines),
                "inline": False
            })

        return fields

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
        profile_url = f"https://vrchat.com/home/user/{user_id}"
        embed = {
            "title": "✅ ユーザー参加",
            "description": f"**[{display_name}]({profile_url})** が参加しました",
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
        profile_url = f"https://vrchat.com/home/user/{user_id}"
        embed = {
            "title": "❌ ユーザー退出",
            "description": f"**[{display_name}]({profile_url})** が退出しました",
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
        # インスタンスリンクを生成
        instance_link = self._create_instance_link(new_instance) if new_instance else None

        fields = [
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
        ]

        # インスタンスリンクを追加
        if instance_link:
            fields.append({
                "name": "🔗 インスタンスリンク",
                "value": f"[VRChatで開く]({instance_link})",
                "inline": False
            })

        embed = {
            "title": "🔄 インスタンス変更",
            "description": f"新しいインスタンスに移動しました",
            "color": 0xf39c12,  # オレンジ色
            "fields": fields,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "VRChat Sugar Checker"
            }
        }
        return self.send(embed=embed)

    def _create_instance_link(self, instance_id: str) -> Optional[str]:
        """
        VRChatインスタンスリンクを生成
        Args:
            instance_id: インスタンスID（例: wrld_xxx:12345~region(jp)~...）
        Returns:
            Optional[str]: VRChatで開けるリンク（生成できない場合はNone）
        """
        if not instance_id:
            return None

        try:
            # インスタンスIDをURLエンコード
            encoded_instance = quote(instance_id, safe='')
            # VRChat起動リンク
            # vrchat://launch?id=wrld_xxx:12345~...
            return f"https://vrchat.com/home/launch?worldId={encoded_instance}"
        except Exception as e:
            logger.error(f"インスタンスリンクの生成に失敗: {e}")
            return None


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
