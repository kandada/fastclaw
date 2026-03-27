"""飞书渠道适配器"""

import asyncio
import json
from typing import Optional

from gateway.channels.base import ChannelAdapter


class FeishuAdapter(ChannelAdapter):
    """飞书渠道适配器

    用于接入飞书消息平台，实现与飞书用户的对话。
    """

    def __init__(self):
        super().__init__("feishu")
        self.app_id = None
        self.app_secret = None
        self.verification_token = None
        self.encrypt_key = None
        self.ws_client = None

    async def connect(self):
        """建立飞书连接"""
        if not self.app_id or not self.app_secret:
            raise ValueError("Feishu app_id and app_secret are required")

        print(f"Connecting to Feishu with app_id: {self.app_id}")

        # 获取 tenant_access_token
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={
                    "app_id": self.app_id,
                    "app_secret": self.app_secret,
                },
            )
            data = response.json()

            if data.get("code") != 0:
                raise Exception(f"Failed to get Feishu token: {data}")

            self.tenant_token = data.get("tenant_access_token")
            print("Feishu connection established")

    async def disconnect(self):
        """断开飞书连接"""
        if self.ws_client:
            await self.ws_client.disconnect()
            self.ws_client = None
        print("Feishu disconnected")

    async def send_message(self, message: str, session_id: str = None):
        """发送消息到飞书

        Args:
            message: 消息内容
            session_id: 飞书用户的 open_id 或 session_id
        """
        if not session_id:
            raise ValueError("session_id is required for Feishu messages")

        import httpx

        headers = {
            "Authorization": f"Bearer {self.tenant_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://open.feishu.cn/open-apis/im/v1/messages",
                headers=headers,
                json={
                    "receive_id": session_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": message}),
                },
                params={"receive_id_type": "open_id"},
            )

            result = response.json()
            if result.get("code") != 0:
                raise Exception(f"Failed to send Feishu message: {result}")

            return result

    async def on_message(self, message: dict):
        """接收飞书消息回调

        Args:
            message: 飞书消息事件字典
        """
        event = message.get("event", {})

        if event.get("message_type") == "text":
            from fastmind import Event

            text_content = json.loads(event.get("content", "{}")).get("text", "")
            sender = (
                event.get("sender", {}).get("sender_id", {}).get("open_id", "unknown")
            )

            feishu_event = Event(
                type="user.message",
                payload={"text": text_content, "channel": "feishu"},
                session_id=sender,
            )

            # 通过 API 发送事件
            from gateway.router import _websocket_api

            if _websocket_api:
                await _websocket_api.push_event(sender, feishu_event)

    def load_config_from_file(self, config_file: str):
        """从文件加载飞书配置"""
        import json
        from pathlib import Path

        config_path = Path(config_file)
        if config_path.exists():
            config = json.loads(config_path.read_text())
            self.load_config(config)
            self.app_id = config.get("app_id")
            self.app_secret = config.get("app_secret")
            self.verification_token = config.get("verification_token")
            self.encrypt_key = config.get("encrypt_key")


class FeishuWebhookHandler:
    """飞书 Webhook 处理器"""

    def __init__(self, adapter: FeishuAdapter):
        self.adapter = adapter

    async def handle(self, body: dict, headers: dict):
        """处理飞书 Webhook 事件

        Args:
            body: 请求体
            headers: 请求头
        """
        # 验证 URL
        if body.get("type") == "url_verification":
            challenge = body.get("challenge", "")
            return {"challenge": challenge}

        # 处理事件
        event = body.get("event", {})
        event_type = event.get("type")

        if event_type == "im.message.receive_v1":
            await self.adapter.on_message(body)

        return {"code": 0}
