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

    def send_with_file(self, file_path: str, content: str = None, embed: Dict = None) -> bool:
        """
        ファイル付きでWebHookを送信
        Args:
            file_path: 送信するファイルのパス
            content: メッセージ本文
            embed: 埋め込み
        Returns:
            bool: 送信成功ならTrue
        """
        try:
            from pathlib import Path
            file_path = Path(file_path)

            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                return False

            payload = {
                "username": self.username,
            }

            if self.avatar_url:
                payload["avatar_url"] = self.avatar_url

            if content:
                payload["content"] = content

            if embed:
                payload["embeds"] = [embed]

            # ファイルをアップロード
            with open(file_path, 'rb') as f:
                files = {
                    'file': (file_path.name, f, 'image/png')
                }

                # payload_jsonとして送信（multipart/form-dataの場合）
                response = requests.post(
                    self.webhook_url,
                    data={'payload_json': json.dumps(payload)},
                    files=files,
                    timeout=30
                )

            if response.status_code == 200 or response.status_code == 204:
                logger.debug(f"Discord通知（ファイル付き）を送信しました: {file_path.name}")
                return True
            else:
                logger.error(f"Discord通知（ファイル付き）の送信に失敗: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Discord通知（ファイル付き）の送信中にエラーが発生: {e}")
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

    def send_instance_changed(self, old_instance: str, new_instance: str, world_name: str, users: dict = None) -> bool:
        """
        インスタンス変更通知を送信
        Args:
            old_instance: 前のインスタンスID
            new_instance: 新しいインスタンスID
            world_name: ワールド名
            users: 既にインスタンスにいるユーザー（display_name → user_id）
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

        # 既存ユーザーリストを追加（80人まで、分割対応）
        if users:
            user_count = len(users)
            fields.append({
                "name": f"👥 既にいるユーザー ({user_count}人)",
                "value": "―" * 30,
                "inline": False
            })

            # ユーザーリストを作成（プロフィールリンク付き）
            user_links = []
            for display_name, user_id in users.items():
                # 表示名を20文字に制限
                display_name_short = display_name[:20] + "..." if len(display_name) > 20 else display_name
                user_link = f"[{display_name_short}](https://vrchat.com/home/user/{user_id})"
                user_links.append(user_link)

            # ユーザーリストを結合（改行区切り）
            user_list_text = "\n".join(user_links)

            # フィールドの文字数制限を確認（1024文字）
            # 超える場合は分割
            if len(user_list_text) <= 900:
                fields.append({
                    "name": "一緒にいるユーザー",
                    "value": user_list_text,
                    "inline": False
                })
            else:
                # 分割処理
                current_text = ""
                field_index = 1
                for user_link in user_links:
                    if len(current_text) + len(user_link) + 1 > 900:  # 1文字は改行分
                        # 現在のフィールドを追加
                        fields.append({
                            "name": f"一緒にいるユーザー (続き {field_index})",
                            "value": current_text,
                            "inline": False
                        })
                        current_text = user_link
                        field_index += 1
                    else:
                        if current_text:
                            current_text += "\n"
                        current_text += user_link

                # 最後のフィールドを追加
                if current_text:
                    fields.append({
                        "name": f"一緒にいるユーザー (続き {field_index})",
                        "value": current_text,
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

    def send_instance_existing_users(self, world_name: str, users: dict) -> bool:
        """
        インスタンス変更時に既にいたユーザーリストを送信（別投稿）
        Args:
            world_name: ワールド名
            users: 既にインスタンスにいたユーザー（display_name → user_id）
        Returns:
            bool: 送信成功ならTrue
        """
        if not users:
            return True  # ユーザーがいない場合はスキップ

        user_count = len(users)
        fields = [
            {
                "name": f"👥 既にいたユーザー ({user_count}人)",
                "value": "―" * 30,
                "inline": False
            }
        ]

        # ユーザーリストを作成（プロフィールリンク付き）
        user_links = []
        for display_name, user_id in users.items():
            # 表示名を20文字に制限
            display_name_short = display_name[:20] + "..." if len(display_name) > 20 else display_name
            user_link = f"[{display_name_short}](https://vrchat.com/home/user/{user_id})"
            user_links.append(user_link)

        # ユーザーリストを結合（改行区切り）
        user_list_text = "\n".join(user_links)

        # フィールドの文字数制限を確認（1024文字）
        # 超える場合は分割
        if len(user_list_text) <= 900:
            fields.append({
                "name": "ユーザーリスト",
                "value": user_list_text,
                "inline": False
            })
        else:
            # 分割処理
            current_text = ""
            field_index = 1
            for user_link in user_links:
                if len(current_text) + len(user_link) + 1 > 900:  # 1文字は改行分
                    # 現在のフィールドを追加
                    fields.append({
                        "name": f"ユーザーリスト (続き {field_index})",
                        "value": current_text,
                        "inline": False
                    })
                    current_text = user_link
                    field_index += 1
                else:
                    if current_text:
                        current_text += "\n"
                    current_text += user_link

            # 最後のフィールドを追加
            if current_text:
                fields.append({
                    "name": f"ユーザーリスト (続き {field_index})",
                    "value": current_text,
                    "inline": False
                })

        embed = {
            "title": "👥 元からいたユーザー",
            "description": f"{world_name or '不明'} に既にいたユーザーたち",
            "color": 0x3498db,  # 青色
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
            # インスタンスIDをURLエンコード（:はエンコードしない）
            encoded_instance = quote(instance_id, safe=':')
            # VRChat起動リンク
            # vrchat://launch?id=wrld_xxx:12345~...
            return f"https://vrchat.com/home/launch?worldId={encoded_instance}"
        except Exception as e:
            logger.error(f"インスタンスリンクの生成に失敗: {e}")
            return None


    def send_file_upload_complete(self, upload_results: list, password: str) -> bool:
        """
        ファイルアップロード完了通知を送信
        Args:
            upload_results: アップロード結果のリスト
            password: ZIP解凍パスワード
        Returns:
            bool: 送信成功ならTrue
        """
        if not upload_results:
            return False

        # 合計サイズを計算
        total_size_mb = sum(result.get('file_size_mb', 0) for result in upload_results)

        fields = []

        # アップロード結果（通常は1つのセッションZIP）
        for i, result in enumerate(upload_results, 1):
            url = result.get('url', '')  # tmpfiles.orgはurlフィールド
            file_name = result.get('file_name', '')
            file_size_mb = result.get('file_size_mb', 0)

            field_value = f"**ファイル名:** `{file_name}`\n"
            field_value += f"**サイズ:** {file_size_mb:.2f} MB\n"
            field_value += f"**ダウンロード:** [tmpfiles.org]({url})\n"
            field_value += f"**有効期限:** 60分間\n"
            field_value += f"**🔐 ZIP解凍パスワード:** `{password}`"

            fields.append({
                "name": f"📦 VRChatセッションアーカイブ",
                "value": field_value,
                "inline": False
            })

        description = f"VRChatセッションの全ファイルをパスワード保護付きZIPでアップロードしました"
        if len(upload_results) == 1:
            description += f"\n合計サイズ: **{total_size_mb:.2f} MB**"

        embed = {
            "title": "📤 ファイルアップロード完了",
            "description": description,
            "color": 0x9b59b6,  # 紫色
            "fields": fields,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "VRChat Sugar Checker | tmpfiles.org (60分間有効)"
            }
        }

        return self.send(embed=embed)

    def send_avatar_detection(self, screenshot_path: str, has_avatars: bool, avatar_count: int,
                              confidence: str, description: str, world_name: str = None) -> bool:
        """
        アバター検出結果通知を送信（画像ファイル付き）
        Args:
            screenshot_path: スクリーンショットのファイルパス
            has_avatars: 他のアバターが検出されたか
            avatar_count: アバター数
            confidence: 確信度
            description: 詳細説明
            world_name: ワールド名
        Returns:
            bool: 送信成功ならTrue
        """
        if not has_avatars:
            return True  # 他のアバターがいない場合は通知しない

        emoji = "👥" if avatar_count > 1 else "🧑"
        color = 0x2ecc71 if confidence == "high" else (0xf39c12 if confidence == "medium" else 0xe74c3c)

        fields = [
            {
                "name": "検出されたアバター数",
                "value": f"{avatar_count}人",
                "inline": True
            },
            {
                "name": "確信度",
                "value": confidence.upper(),
                "inline": True
            },
            {
                "name": "詳細",
                "value": description,
                "inline": False
            }
        ]

        if world_name:
            fields.insert(0, {
                "name": "🌍 ワールド",
                "value": world_name,
                "inline": False
            })

        embed = {
            "title": f"{emoji} 他のアバターを検出しました",
            "color": color,
            "fields": fields,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "VRChat Sugar Checker | AI Avatar Detection"
            }
        }
        return self.send_with_file(screenshot_path, embed=embed)

    def send_screenshot_notification(self, screenshot_path: str, world_name: str = None,
                                     reason: str = None) -> bool:
        """
        スクリーンショット撮影通知を送信（AI機能OFF時用、画像ファイル付き）
        Args:
            screenshot_path: スクリーンショットのファイルパス
            world_name: ワールド名
            reason: 撮影理由（例: "instance_change", "auto_capture"）
        Returns:
            bool: 送信成功ならTrue
        """
        reason_text = {
            "instance_change": "インスタンス変更時",
            "auto_capture": "定期自動撮影",
            "manual": "手動撮影"
        }.get(reason, "")

        fields = []

        if world_name:
            fields.append({
                "name": "🌍 ワールド",
                "value": world_name,
                "inline": False
            })

        if reason_text:
            fields.append({
                "name": "📍 撮影タイミング",
                "value": reason_text,
                "inline": True
            })

        embed = {
            "title": "📸 スクリーンショット撮影",
            "color": 0x3498db,  # 青色
            "fields": fields,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "VRChat Sugar Checker | Screenshot"
            }
        }
        return self.send_with_file(screenshot_path, embed=embed)

    def send_conversation_summary(self, world_name: str, topics: List[str], summary: str,
                                   decisions: Optional[List[str]], promises: Optional[List[str]],
                                   duration_minutes: int = None) -> bool:
        """
        会話内容サマリ通知を送信
        Args:
            world_name: ワールド名
            topics: トピック一覧
            summary: 会話内容の概要
            decisions: 決めたこと
            promises: 約束したこと
            duration_minutes: 録音時間（分）
        Returns:
            bool: 送信成功ならTrue
        """
        fields = [
            {
                "name": "🌍 ワールド",
                "value": world_name or "不明",
                "inline": False
            },
            {
                "name": "📋 トピック",
                "value": "\n".join([f"• {topic}" for topic in topics]) if topics else "なし",
                "inline": False
            },
            {
                "name": "💬 会話内容の概要",
                "value": summary,
                "inline": False
            }
        ]

        if decisions:
            fields.append({
                "name": "✅ 決めたこと",
                "value": "\n".join([f"• {decision}" for decision in decisions]),
                "inline": False
            })

        if promises:
            fields.append({
                "name": "🤝 約束したこと",
                "value": "\n".join([f"• {promise}" for promise in promises]),
                "inline": False
            })

        if duration_minutes:
            fields.append({
                "name": "⏱️ 録音時間",
                "value": f"{duration_minutes}分",
                "inline": True
            })

        embed = {
            "title": "🎙️ 会話内容サマリ",
            "color": 0x9b59b6,  # 紫色
            "fields": fields,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "VRChat Sugar Checker | AI Conversation Analysis"
            }
        }
        return self.send(embed=embed)

    def send_no_conversation(self, world_name: str, reason: str) -> bool:
        """
        会話がなかった場合の通知を送信
        Args:
            world_name: ワールド名
            reason: スキップした理由
        Returns:
            bool: 送信成功ならTrue
        """
        embed = {
            "title": "🔇 会話なし",
            "description": "このワールドでは会話が検出されませんでした",
            "color": 0x95a5a6,  # グレー
            "fields": [
                {
                    "name": "🌍 ワールド",
                    "value": world_name or "不明",
                    "inline": False
                },
                {
                    "name": "📊 スキップ理由",
                    "value": reason,
                    "inline": False
                },
                {
                    "name": "💰 コスト削減",
                    "value": "AI分析をスキップしてコストを節約しました",
                    "inline": False
                }
            ],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "VRChat Sugar Checker | AI Conversation Analysis"
            }
        }
        return self.send(embed=embed)

    def send_time_summary(self, world_name: str, instance_id: str, total_duration: str,
                          user_times: Dict[str, str]) -> bool:
        """
        インスタンス離脱時の滞在時間サマリ通知を送信（複数投稿に分割）
        Args:
            world_name: ワールド名
            instance_id: インスタンスID
            total_duration: 総滞在時間（HH:MM:SS形式）
            user_times: ユーザー毎の一緒にいた時間 {display_name: duration_str}
        Returns:
            bool: 送信成功ならTrue
        """
        # 滞在時間でソート（長い順）
        sorted_users = sorted(user_times.items(), key=lambda x: x[1], reverse=True) if user_times else []

        # ユーザーリストをフィールドサイズ制限（1024文字）ごとに分割
        user_chunks = self._split_users_into_chunks(sorted_users, max_length=1024)

        # 最初のEmbed（サマリ情報含む）
        first_fields = [
            {
                "name": "🌍 ワールド",
                "value": world_name or "不明",
                "inline": False
            },
            {
                "name": "⏱️ 総滞在時間",
                "value": total_duration,
                "inline": True
            },
            {
                "name": "👥 一緒にいた人数",
                "value": f"{len(user_times)}人",
                "inline": True
            }
        ]

        # 最初のユーザーチャンクを追加
        if user_chunks:
            first_fields.append({
                "name": f"🕐 ユーザー毎の滞在時間 (1/{len(user_chunks)})",
                "value": user_chunks[0],
                "inline": False
            })

        first_embed = {
            "title": "👋 インスタンスを離れました",
            "description": "滞在時間のサマリです",
            "color": 0x95a5a6,  # グレー
            "fields": first_fields,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "VRChat Sugar Checker | Time Tracking"
            }
        }

        # 最初のEmbedを送信
        success = self.send(embed=first_embed)
        if not success:
            return False

        # 残りのユーザーチャンクを追加のEmbedとして送信
        for i, chunk in enumerate(user_chunks[1:], start=2):
            additional_embed = {
                "color": 0x95a5a6,
                "fields": [
                    {
                        "name": f"🕐 ユーザー毎の滞在時間 (続き {i}/{len(user_chunks)})",
                        "value": chunk,
                        "inline": False
                    }
                ],
                "footer": {
                    "text": "VRChat Sugar Checker | Time Tracking"
                }
            }
            success = self.send(embed=additional_embed)
            if not success:
                logger.warning(f"Failed to send time summary chunk {i}/{len(user_chunks)}")

        return True

    def _split_users_into_chunks(self, sorted_users: list, max_length: int = 1024) -> list:
        """
        ユーザーリストをDiscord fieldの文字数制限に合わせて分割
        Args:
            sorted_users: ソート済みユーザーリスト [(display_name, duration), ...]
            max_length: 最大文字数（デフォルト: 1024）
        Returns:
            list: 分割されたテキストのリスト
        """
        chunks = []
        current_chunk = []
        current_length = 0

        for display_name, duration in sorted_users:
            line = f"• {display_name}: {duration}"
            line_length = len(line) + 1  # +1 for newline

            # 現在のチャンクに追加すると制限を超える場合
            if current_length + line_length > max_length and current_chunk:
                # 現在のチャンクを保存
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_length = 0

            # 行を追加
            current_chunk.append(line)
            current_length += line_length

        # 最後のチャンクを追加
        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return chunks


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
