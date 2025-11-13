#!/usr/bin/env python3
"""
Discord Bot モジュール
テキストチャットと音声通話機能を提供
別プロセスとして動作し、main.pyと連携
"""

import logging
import asyncio
import discord
from discord.ext import commands
from pathlib import Path
from typing import Optional, Dict
import multiprocessing
import queue
import signal
import sys
import json

# VRChat音声ストリーミング
try:
    import sys
    from pathlib import Path
    # モジュールパスを追加
    module_path = Path(__file__).parent.parent
    if str(module_path) not in sys.path:
        sys.path.insert(0, str(module_path))

    from discord.vrchat_audio_source import VRChatAudioSource, get_vrchat_pid
    VRCHAT_AUDIO_AVAILABLE = True
except ImportError as e:
    VRCHAT_AUDIO_AVAILABLE = False
    logging.warning(f"VRChat audio streaming not available: {e}")

logger = logging.getLogger(__name__)


class VRChatSugarBot(commands.Bot):
    """VRChat Sugar Checker Discord Bot"""

    def __init__(self, config: Dict, message_queue: multiprocessing.Queue):
        """
        初期化
        Args:
            config: ボット設定
            message_queue: プロセス間通信用のキュー
        """
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True

        super().__init__(
            command_prefix=config.get('command_prefix', '!'),
            intents=intents,
            help_command=None
        )

        self.config = config
        self.message_queue = message_queue
        self.voice_client: Optional[discord.VoiceClient] = None
        self.is_running = False
        self.should_stop = False

        # VRChatの状態（main.pyから受信）
        self.vrchat_status = {
            'instance': None,
            'world': None,
            'users': [],
            'is_running': False
        }

        # VRChat音声ストリーミング
        self.vrchat_audio_source: Optional['VRChatAudioSource'] = None
        self.is_streaming_vrchat_audio = False

        # コマンドを登録
        self.setup_commands()

        logger.info("VRChatSugarBot initialized")

    def setup_commands(self):
        """コマンドをセットアップ"""

        @self.command(name='help', aliases=['h'])
        async def help_command(ctx):
            """ヘルプを表示"""
            embed = discord.Embed(
                title="VRChat Sugar Checker Bot - コマンド一覧",
                description="利用可能なコマンド",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="!help / !h",
                value="このヘルプを表示",
                inline=False
            )
            embed.add_field(
                name="!join / !j",
                value="ボイスチャンネルに参加",
                inline=False
            )
            embed.add_field(
                name="!leave / !l",
                value="ボイスチャンネルから退出",
                inline=False
            )
            embed.add_field(
                name="!status / !s",
                value="VRChatの現在の状態を表示",
                inline=False
            )
            embed.add_field(
                name="!ping",
                value="ボットの応答速度を確認",
                inline=False
            )

            await ctx.send(embed=embed)

        @self.command(name='join', aliases=['j'])
        async def join_voice(ctx):
            """ボイスチャンネルに参加してVRChat音声をストリーミング"""
            if not ctx.author.voice:
                await ctx.send("❌ ボイスチャンネルに接続してください")
                return

            channel = ctx.author.voice.channel

            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.move_to(channel)
                await ctx.send(f"✅ {channel.name} に移動しました")
            else:
                self.voice_client = await channel.connect()
                await ctx.send(f"✅ {channel.name} に参加しました")

            logger.info(f"Joined voice channel: {channel.name}")

            # VRChat音声ストリーミングを開始
            if self.config.get('voice_enabled', True):
                success = await self.start_vrchat_audio_stream()
                if success:
                    await ctx.send("🎵 VRChat音声のストリーミングを開始しました")
                else:
                    await ctx.send("⚠️ VRChat音声のストリーミングを開始できませんでした")

        @self.command(name='leave', aliases=['l'])
        async def leave_voice(ctx):
            """ボイスチャンネルから退出"""
            if not self.voice_client or not self.voice_client.is_connected():
                await ctx.send("❌ ボイスチャンネルに接続していません")
                return

            # VRChat音声ストリーミングを停止
            await self.stop_vrchat_audio_stream()

            await self.voice_client.disconnect()
            self.voice_client = None
            await ctx.send("✅ ボイスチャンネルから退出しました")
            logger.info("Left voice channel")

        @self.command(name='status', aliases=['s'])
        async def status_command(ctx):
            """VRChatの状態を表示"""
            embed = discord.Embed(
                title="VRChat Sugar Checker - 現在の状態",
                color=discord.Color.green() if self.vrchat_status['is_running'] else discord.Color.red()
            )

            if self.vrchat_status['is_running']:
                embed.add_field(
                    name="VRChat",
                    value="✅ 起動中",
                    inline=False
                )

                if self.vrchat_status['world']:
                    embed.add_field(
                        name="現在のワールド",
                        value=self.vrchat_status['world'],
                        inline=False
                    )

                if self.vrchat_status['instance']:
                    embed.add_field(
                        name="インスタンスID",
                        value=f"`{self.vrchat_status['instance']}`",
                        inline=False
                    )

                user_count = len(self.vrchat_status['users'])
                if user_count > 0:
                    users_list = ', '.join(self.vrchat_status['users'][:10])
                    if user_count > 10:
                        users_list += f" ...他{user_count - 10}名"
                    embed.add_field(
                        name=f"ユーザー ({user_count}名)",
                        value=users_list,
                        inline=False
                    )
            else:
                embed.add_field(
                    name="VRChat",
                    value="❌ 停止中",
                    inline=False
                )

            await ctx.send(embed=embed)

        @self.command(name='ping')
        async def ping_command(ctx):
            """レイテンシを確認"""
            latency = round(self.latency * 1000)
            await ctx.send(f"🏓 Pong! レイテンシ: {latency}ms")

    async def on_ready(self):
        """ボット起動時の処理"""
        logger.info(f"Bot is ready! Logged in as {self.user.name}")
        logger.info(f"Bot ID: {self.user.id}")

        # ステータスを設定
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="VRChat Activity"
        )
        await self.change_presence(activity=activity)

    async def on_message(self, message):
        """メッセージ受信時の処理"""
        # 自分自身のメッセージは無視
        if message.author == self.user:
            return

        # コマンドを処理
        await self.process_commands(message)

    async def on_voice_state_update(self, member, before, after):
        """ボイス状態変更時の処理"""
        # ボットが一人になったら自動退出
        if self.voice_client and self.voice_client.is_connected():
            # ボットがいるチャンネルのメンバー数をチェック
            channel = self.voice_client.channel
            members = [m for m in channel.members if not m.bot]

            if len(members) == 0:
                logger.info("No members in voice channel, leaving...")
                await self.voice_client.disconnect()
                self.voice_client = None

    async def process_message_queue(self):
        """メッセージキューを処理（main.pyからの指示を受信）"""
        while not self.should_stop:
            try:
                # タイムアウト付きでキューから取得
                if not self.message_queue.empty():
                    message = self.message_queue.get_nowait()

                    if message['type'] == 'shutdown':
                        logger.info("Received shutdown signal")
                        self.should_stop = True
                        await self.close()
                        break

                    elif message['type'] == 'update_status':
                        # VRChatの状態を更新
                        self.vrchat_status.update(message['data'])
                        logger.debug(f"Updated VRChat status: {self.vrchat_status}")

                    elif message['type'] == 'send_message':
                        # テキストメッセージを送信
                        await self.send_text_message(
                            message['channel_id'],
                            content=message.get('content'),
                            embed=message.get('embed')
                        )

                    elif message['type'] == 'send_file':
                        # ファイルを送信
                        await self.send_file(
                            message['channel_id'],
                            Path(message['file_path']),
                            content=message.get('content')
                        )

                await asyncio.sleep(0.1)  # CPU負荷軽減

            except queue.Empty:
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Error processing message queue: {e}")
                await asyncio.sleep(1)

    async def send_text_message(self, channel_id: int, content: str = None, embed: discord.Embed = None):
        """
        テキストメッセージを送信
        Args:
            channel_id: チャンネルID
            content: メッセージ内容
            embed: 埋め込みメッセージ
        """
        try:
            channel = self.get_channel(channel_id)
            if not channel:
                logger.error(f"Channel not found: {channel_id}")
                return

            await channel.send(content=content, embed=embed)
            logger.debug(f"Sent message to channel {channel_id}")
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    async def send_file(self, channel_id: int, file_path: Path, content: str = None):
        """
        ファイルを送信
        Args:
            channel_id: チャンネルID
            file_path: ファイルパス
            content: 添付メッセージ
        """
        try:
            channel = self.get_channel(channel_id)
            if not channel:
                logger.error(f"Channel not found: {channel_id}")
                return

            with open(file_path, 'rb') as f:
                discord_file = discord.File(f, filename=file_path.name)
                await channel.send(content=content, file=discord_file)

            logger.debug(f"Sent file to channel {channel_id}: {file_path.name}")
        except Exception as e:
            logger.error(f"Error sending file: {e}")

    async def play_audio(self, audio_path: Path):
        """
        音声を再生
        Args:
            audio_path: 音声ファイルのパス
        """
        if not self.voice_client or not self.voice_client.is_connected():
            logger.warning("Not connected to voice channel")
            return

        try:
            # 既に再生中なら停止
            if self.voice_client.is_playing():
                self.voice_client.stop()

            # 音声を再生
            audio_source = discord.FFmpegPCMAudio(str(audio_path))
            self.voice_client.play(audio_source)
            logger.info(f"Playing audio: {audio_path.name}")
        except Exception as e:
            logger.error(f"Error playing audio: {e}")

    async def start_vrchat_audio_stream(self) -> bool:
        """
        VRChat音声のストリーミングを開始
        Returns:
            bool: 成功した場合True
        """
        if not VRCHAT_AUDIO_AVAILABLE:
            logger.error("VRChat audio streaming not available")
            return False

        if not self.voice_client or not self.voice_client.is_connected():
            logger.warning("Not connected to voice channel")
            return False

        if self.is_streaming_vrchat_audio:
            logger.warning("Already streaming VRChat audio")
            return True

        try:
            # VRChatのPIDを取得
            vrchat_pid = await asyncio.get_event_loop().run_in_executor(None, get_vrchat_pid)

            if not vrchat_pid:
                logger.error("VRChat process not found")
                return False

            # VRChatAudioSourceを作成
            self.vrchat_audio_source = VRChatAudioSource(vrchat_pid)

            # 音声キャプチャを開始（別スレッドで）
            success = await asyncio.get_event_loop().run_in_executor(
                None,
                self.vrchat_audio_source.start
            )

            if not success:
                logger.error("Failed to start VRChat audio capture")
                self.vrchat_audio_source = None
                return False

            # 既に再生中なら停止
            if self.voice_client.is_playing():
                self.voice_client.stop()

            # Discordで再生
            self.voice_client.play(
                self.vrchat_audio_source,
                after=lambda e: logger.error(f'VRChat audio stream error: {e}') if e else None
            )

            self.is_streaming_vrchat_audio = True
            logger.info("VRChat audio streaming started")
            return True

        except Exception as e:
            logger.error(f"Error starting VRChat audio stream: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def stop_vrchat_audio_stream(self):
        """VRChat音声のストリーミングを停止"""
        if not self.is_streaming_vrchat_audio:
            return

        try:
            # 再生を停止
            if self.voice_client and self.voice_client.is_playing():
                self.voice_client.stop()

            # AudioSourceをクリーンアップ
            if self.vrchat_audio_source:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.vrchat_audio_source.cleanup
                )
                self.vrchat_audio_source = None

            self.is_streaming_vrchat_audio = False
            logger.info("VRChat audio streaming stopped")

        except Exception as e:
            logger.error(f"Error stopping VRChat audio stream: {e}")

    async def start_with_queue_processing(self, token: str):
        """
        ボットを起動してメッセージキューの処理を開始
        Args:
            token: Discord Bot Token
        """
        try:
            self.is_running = True

            # メッセージキュー処理タスクを起動
            queue_task = asyncio.create_task(self.process_message_queue())

            # ボットを起動
            await self.start(token)

            # ボット終了後、キュータスクもキャンセル
            queue_task.cancel()
            try:
                await queue_task
            except asyncio.CancelledError:
                pass

        except Exception as e:
            logger.error(f"Error in bot: {e}")
        finally:
            self.is_running = False


def run_bot_process(config: Dict, message_queue: multiprocessing.Queue, log_queue: multiprocessing.Queue):
    """
    別プロセスでボットを実行
    Args:
        config: ボット設定
        message_queue: メインプロセスからの指示を受け取るキュー
        log_queue: ログをメインプロセスに送信するキュー
    """
    # ログ設定（キューハンドラを使用）
    from logging.handlers import QueueHandler
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    queue_handler = QueueHandler(log_queue)
    root_logger.addHandler(queue_handler)

    logger.info("Bot process started")

    # シグナルハンドラを設定（Ctrl+Cなどで終了）
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down bot process...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    token = config.get('token')
    if not token or token == 'YOUR_BOT_TOKEN':
        logger.error("Discord bot token not configured")
        return

    try:
        # イベントループを作成
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # ボットを作成
        bot = VRChatSugarBot(config, message_queue)

        # ボットを起動
        loop.run_until_complete(bot.start_with_queue_processing(token))

    except Exception as e:
        logger.error(f"Error in bot process: {e}", exc_info=True)
    finally:
        logger.info("Bot process terminated")


class BotProcessManager:
    """Discord Botプロセス管理クラス"""

    def __init__(self, config: Dict, log_queue: multiprocessing.Queue):
        """
        初期化
        Args:
            config: ボット設定
            log_queue: ログキュー（main.pyと共有）
        """
        self.config = config
        self.log_queue = log_queue
        self.process: Optional[multiprocessing.Process] = None
        self.message_queue: Optional[multiprocessing.Queue] = None

    def start(self):
        """ボットプロセスを起動"""
        if not self.config.get('enabled', False):
            logger.info("Discord bot is disabled")
            return

        try:
            # メッセージキューを作成
            self.message_queue = multiprocessing.Queue()

            # ボットプロセスを起動
            self.process = multiprocessing.Process(
                target=run_bot_process,
                args=(self.config, self.message_queue, self.log_queue),
                name="DiscordBot"
            )
            self.process.start()

            logger.info(f"Discord bot process started (PID: {self.process.pid})")

        except Exception as e:
            logger.error(f"Error starting Discord bot process: {e}")

    def stop(self):
        """ボットプロセスを停止"""
        if self.process and self.process.is_alive():
            try:
                # 終了メッセージを送信
                self.send_message({'type': 'shutdown'})

                # プロセスが終了するまで待機（最大5秒）
                self.process.join(timeout=5)

                # まだ生きていたら強制終了
                if self.process.is_alive():
                    logger.warning("Bot process did not terminate gracefully, forcing...")
                    self.process.terminate()
                    self.process.join(timeout=2)

                    if self.process.is_alive():
                        logger.error("Bot process still alive, killing...")
                        self.process.kill()
                        self.process.join()

                logger.info("Discord bot process stopped")

            except Exception as e:
                logger.error(f"Error stopping Discord bot process: {e}")

    def send_message(self, message: Dict):
        """
        ボットプロセスにメッセージを送信
        Args:
            message: メッセージ辞書
        """
        if self.message_queue:
            try:
                self.message_queue.put_nowait(message)
            except Exception as e:
                logger.error(f"Error sending message to bot process: {e}")

    def update_vrchat_status(self, instance: str = None, world: str = None,
                            users: list = None, is_running: bool = False):
        """
        VRChatの状態をボットに通知
        Args:
            instance: インスタンスID
            world: ワールド名
            users: ユーザーリスト
            is_running: VRChatが起動中か
        """
        self.send_message({
            'type': 'update_status',
            'data': {
                'instance': instance,
                'world': world,
                'users': users or [],
                'is_running': is_running
            }
        })

    def send_text_message(self, channel_id: int, content: str = None, embed: Dict = None):
        """
        テキストメッセージを送信
        Args:
            channel_id: チャンネルID
            content: メッセージ内容
            embed: 埋め込みメッセージ（辞書形式）
        """
        self.send_message({
            'type': 'send_message',
            'channel_id': channel_id,
            'content': content,
            'embed': embed
        })

    def send_file(self, channel_id: int, file_path: str, content: str = None):
        """
        ファイルを送信
        Args:
            channel_id: チャンネルID
            file_path: ファイルパス
            content: 添付メッセージ
        """
        self.send_message({
            'type': 'send_file',
            'channel_id': channel_id,
            'file_path': file_path,
            'content': content
        })
