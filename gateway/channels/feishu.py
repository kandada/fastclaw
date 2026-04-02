"""飞书渠道适配器（长连接模式，使用 lark-oapi SDK）"""

import asyncio
import json
import threading
from typing import Optional

import lark_oapi as lark
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from gateway.channels.base import ChannelAdapter

# 全局事件处理函数（SDK要求使用普通函数）
_feishu_adapter = None
_main_loop = None


def set_main_loop(loop):
    """设置主事件循环供飞书回调使用"""
    global _main_loop
    _main_loop = loop


def _on_feishu_message_receive(data: P2ImMessageReceiveV1):
    """飞书消息回调"""
    if _feishu_adapter is None:
        print("[Feishu] Error: adapter not initialized")
        return

    async def process():
        await _feishu_adapter._handle_feishu_message(data)

    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(process())
            else:
                loop.run_until_complete(process())
        except RuntimeError:
            asyncio.run(process())
    except Exception as e:
        print(f"[Feishu] Callback error: {e}")


class FeishuAdapter(ChannelAdapter):
    """飞书渠道适配器（长连接）"""

    def __init__(self):
        super().__init__("feishu")
        self.app_id = None
        self.app_secret = None
        self.verification_token = None
        self.encrypt_key = None
        self.tenant_token = None
        self._ws_client = None
        self._ws_thread = None
        self._user_current_session = {}

    async def _handle_feishu_message(self, data: P2ImMessageReceiveV1):
        """处理飞书消息事件"""
        try:
            message = data.event.message
            if not message:
                print("[Feishu] No message in event")
                return

            message_type = getattr(message, "message_type", None)
            content = getattr(message, "content", "")
            sender = data.event.sender
            sender_id = sender.sender_id.open_id if sender and sender.sender_id else ""

            print(f"[Feishu] Message: sender_id={sender_id}, type={message_type}")

            if message_type == "text" and content:
                try:
                    content_obj = json.loads(content)
                    text_content = content_obj.get("text", "")
                except:
                    text_content = content

                if text_content and sender_id:
                    from gateway.router import _websocket_api
                    from gateway.channels.handlers import handle_channel_message

                    effective_sender_id = self._user_current_session.get(
                        sender_id, sender_id
                    )

                    async def feishu_send(msg, session_id):
                        await self.send_message(msg, open_id=sender_id)

                    _, session_id = await handle_channel_message(
                        channel_name="feishu",
                        sender_id=effective_sender_id,
                        text_content=text_content,
                        api=_websocket_api,
                        send_func=feishu_send,
                    )

                    if session_id != effective_sender_id:
                        self._user_current_session[sender_id] = session_id
        except Exception as e:
            print(f"[Feishu] Error handling message: {e}")

    async def connect(self):
        """建立飞书长连接"""
        global _feishu_adapter

        if not self.app_id or not self.app_secret:
            raise ValueError("Feishu app_id and app_secret are required")

        print(f"Connecting to Feishu with app_id: {self.app_id}")

        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={
                    "app_id": self.app_id,
                    "app_secret": self.app_secret,
                },
                timeout=30.0,
            )
            data = response.json()

            if data.get("code") != 0:
                raise Exception(f"Failed to get Feishu token: {data}")

            self.tenant_token = data.get("tenant_access_token")

        _feishu_adapter = self

        handler = (
            EventDispatcherHandler.builder("", lark.LogLevel.INFO)
            .register_p2_im_message_receive_v1(_on_feishu_message_receive)
            .build()
        )

        self._ws_client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=handler,
            log_level=lark.LogLevel.INFO,
        )

        def run_ws():
            self._ws_client.start()

        self._ws_thread = threading.Thread(target=run_ws, daemon=True)
        self._ws_thread.start()

        print("Feishu connection established (long connection mode)")

    async def disconnect(self):
        """断开飞书连接"""
        print("Feishu disconnected")

    async def send_message(
        self, message: str, open_id: str = None, chat_id: str = None
    ):
        """发送消息到飞书"""
        receive_id = open_id or chat_id
        if not receive_id:
            raise ValueError("open_id or chat_id is required")

        import httpx

        headers = {
            "Authorization": f"Bearer {self.tenant_token}",
            "Content-Type": "application/json",
        }

        receive_id_type = "open_id" if open_id else "chat_id"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://open.feishu.cn/open-apis/im/v1/messages",
                headers=headers,
                json={
                    "receive_id": receive_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": message}),
                },
                params={"receive_id_type": receive_id_type},
            )

            result = response.json()
            if result.get("code") != 0:
                print(f"[Feishu] Send failed: {result}")
                raise Exception(f"Failed to send Feishu message: {result}")

            return result

    async def on_message(self, message: dict):
        """接收消息回调"""
        pass

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
        return {"code": 0}
