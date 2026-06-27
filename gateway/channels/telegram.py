# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""Telegram 渠道适配器"""

import asyncio
import json
from typing import Optional

import httpx

from gateway.channels.base import ChannelAdapter


class TelegramAdapter(ChannelAdapter):
    """Telegram 渠道适配器

    通过 Telegram Bot API 实现与用户的对话。
    """

    def __init__(self):
        super().__init__("telegram")
        self.bot_token = None
        self.api_base = "https://api.telegram.org"
        self.offset = 0
        self.polling_task = None

    async def connect(self):
        """建立 Telegram 连接"""
        if not self.bot_token:
            raise ValueError("Telegram bot_token is required")

        print(f"Connecting to Telegram bot...")

        me = await self._make_request("getMe")
        if me.get("ok"):
            print(f"Telegram bot connected: @{me['result']['username']}")
        else:
            raise Exception(f"Failed to connect to Telegram: {me}")

    async def disconnect(self):
        """断开 Telegram 连接"""
        if self.polling_task:
            self.polling_task.cancel()
            self.polling_task = None
        print("Telegram disconnected")

    async def _make_request(self, method: str, data: dict = None) -> dict:
        """发送 API 请求"""
        url = f"{self.api_base}/bot{self.bot_token}/{method}"

        async with httpx.AsyncClient() as client:
            if data:
                response = await client.post(url, json=data)
            else:
                response = await client.get(url)

            return response.json()

    async def send_message(self, message: str, session_id: str = None):
        """发送消息到 Telegram

        Args:
            message: 消息内容
            session_id: 格式为 telegram_{chat_id}
        """
        if not session_id:
            raise ValueError("session_id is required for Telegram messages")

        chat_id = (
            session_id.replace("telegram_", "")
            if session_id.startswith("telegram_")
            else session_id
        )

        result = await self._make_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
            },
        )

        if not result.get("ok"):
            raise Exception(f"Failed to send Telegram message: {result}")

        return result

    async def on_message(self, message: dict):
        """接收消息回调

        Args:
            message: Telegram 更新事件字典
        """
        from fastmind import Event

        update_id = message.get("update_id")

        if message.get("message"):
            msg = message["message"]
            chat_id = str(msg["chat"]["id"])
            text = msg.get("text", "")
            session_id = f"telegram_{chat_id}"

            if text:
                telegram_event = Event(
                    type="user.message",
                    payload={"text": text, "channel": "telegram"},
                    session_id=session_id,
                )

                from gateway.router import _websocket_api

                if _websocket_api:
                    await _websocket_api.push_event(session_id, telegram_event)

        return update_id

    async def start_polling(self, callback=None):
        """开始轮询获取更新

        Args:
            callback: 消息回调函数
        """
        while True:
            try:
                updates = await self._make_request(
                    "getUpdates",
                    {"offset": self.offset, "timeout": 60},
                )

                if updates.get("ok"):
                    for update in updates.get("result", []):
                        if callback:
                            await callback(update)
                        else:
                            await self.on_message(update)

                        self.offset = update.get("update_id", 0) + 1

            except Exception as e:
                print(f"Polling error: {e}")
                await asyncio.sleep(5)

    def load_config_from_file(self, config_file: str):
        """从文件加载 Telegram 配置"""
        from pathlib import Path

        config_path = Path(config_file)
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.load_config(config)
            self.bot_token = config.get("bot_token")


class TelegramWebhookHandler:
    """Telegram Webhook 处理器"""

    def __init__(self, adapter: TelegramAdapter):
        self.adapter = adapter

    async def handle(self, body: dict):
        """处理 Telegram Webhook 请求

        Args:
            body: 请求体（JSON）
        """
        return await self.adapter.on_message(body)

    async def set_webhook(self, webhook_url: str):
        """设置 Webhook URL

        Args:
            webhook_url: Webhook 端点 URL
        """
        result = await self.adapter._make_request(
            "setWebhook",
            {"url": webhook_url},
        )
        return result

    async def delete_webhook(self):
        """删除 Webhook"""
        result = await self.adapter._make_request("deleteWebhook")
        return result
