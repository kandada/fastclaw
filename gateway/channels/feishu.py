"""飞书渠道适配器（长连接模式，使用 lark-oapi SDK）"""

import asyncio
import json
import threading
from pathlib import Path
from typing import Optional

import lark_oapi as lark
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from gateway.channels.base import ChannelAdapter
from gateway.channels.client import BaseHttpClient, TokenManager, OAuthHelper

CONFIG_PATH = "workspace/data/channels/feishu_config.json"


class FeishuAdapter(ChannelAdapter, BaseHttpClient):
    """飞书渠道适配器（长连接 + API）"""

    def __init__(self):
        ChannelAdapter.__init__(self, "feishu")
        BaseHttpClient.__init__(self, CONFIG_PATH)

        self.app_id = self.config.get("app_id")
        self.app_secret = self.config.get("app_secret")
        self.verification_token = self.config.get("verification_token")
        self.encrypt_key = self.config.get("encrypt_key")

        self._tenant_token_mgr = TokenManager(self, "tenant")
        self._user_token_mgr = TokenManager(self, "user")
        self._oauth_helper = OAuthHelper(self)

        self._ws_client = None
        self._ws_thread = None
        self._user_current_session = {}

        self._tenant_token = None

    @property
    def tenant_token(self) -> str:
        token = self._tenant_token_mgr.get_token()
        if not token:
            token = self._get_tenant_token_sync()
        return token

    def _get_tenant_token_sync(self) -> str:
        import httpx

        resp = httpx.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=30,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"Failed to get tenant token: {data}")
        token = data.get("tenant_access_token")
        self._tenant_token_mgr.set_token(token, data.get("expire", 7200))
        return token

    async def _get_tenant_token(self) -> str:
        token = self._tenant_token_mgr.get_token()
        if not token:
            resp = await self._post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
            if resp.get("code") != 0:
                raise Exception(f"Failed to get tenant token: {resp}")
            token = resp.get("tenant_access_token")
            self._tenant_token_mgr.set_token(token, resp.get("expire", 7200))
        return token

    def get_user_access_token(self) -> Optional[str]:
        return self._user_token_mgr.get_token()

    def set_user_access_token(
        self, token: str, refresh_token: str = None, expires_in: int = None
    ):
        self._user_token_mgr.set_token(token, expires_in)
        if refresh_token:
            self.config["user_refresh_token"] = refresh_token
            self._save_config()

    def get_user_refresh_token(self) -> Optional[str]:
        return self.config.get("user_refresh_token")

    def get_auth_url(
        self,
        redirect_uri: str = None,
        scope: str = "wiki:wiki:readonly",
        state: str = "auth",
    ) -> str:
        """通过 API 获取授权 URL"""
        import httpx

        app_id = self.config.get("app_id")
        if not app_id:
            raise ValueError("app_id not configured")
        if not redirect_uri:
            redirect_uri = "https://open.feishu.cn/connect/qrcode/connect/callback"

        params = {
            "app_id": app_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
        }

        resp = httpx.get(
            "https://open.feishu.cn/open-apis/authen/v1/authorize",
            params=params,
            headers={"Authorization": f"Bearer {self.tenant_token}"},
            follow_redirects=True,
        )
        return str(resp.url)

    async def exchange_user_token(self, code: str) -> dict:
        resp = await self._oauth_helper.exchange_code_for_token(code)
        if resp.get("code") != 0:
            return resp
        data = resp.get("data", {})
        self.set_user_access_token(
            data.get("access_token"),
            data.get("refresh_token"),
            data.get("expires_in"),
        )
        return resp

    async def refresh_user_token(self) -> dict:
        refresh_token = self.get_user_refresh_token()
        if not refresh_token:
            return {"code": 1, "msg": "No refresh token available"}
        resp = await self._oauth_helper.refresh_user_token(refresh_token)
        if resp.get("code") != 0:
            return resp
        data = resp.get("data", {})
        self.set_user_access_token(
            data.get("access_token"),
            data.get("refresh_token"),
            data.get("expires_in"),
        )
        return resp

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
        if not self.app_id or not self.app_secret:
            raise ValueError("Feishu app_id and app_secret are required")

        print(f"Connecting to Feishu with app_id: {self.app_id}")

        self._tenant_token = await self._get_tenant_token()

        global _feishu_adapter
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

        self._tenant_token = await self._get_tenant_token()
        headers = {
            "Authorization": f"Bearer {self._tenant_token}",
            "Content-Type": "application/json",
        }

        receive_id_type = "open_id" if open_id else "chat_id"

        resp = await self._post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            json={
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": message}),
            },
            params={"receive_id_type": receive_id_type},
            headers=headers,
        )

        if resp.get("code") != 0:
            raise Exception(f"Failed to send Feishu message: {resp}")

        return resp

    async def on_message(self, message: dict):
        """接收消息回调"""
        pass

    def load_config_from_file(self, config_file: str):
        """从文件加载飞书配置"""
        config_path = Path(config_file)
        if config_path.exists():
            config = json.loads(config_path.read_text())
            self.load_config(config)
            self.app_id = config.get("app_id")
            self.app_secret = config.get("app_secret")
            self.verification_token = config.get("verification_token")
            self.encrypt_key = config.get("encrypt_key")

    async def create_document(
        self, title: str = None, folder_token: str = None
    ) -> dict:
        """创建云文档"""
        token = await self._get_tenant_token()
        resp = await self._post(
            "https://open.feishu.cn/open-apis/docx/v1/documents",
            json={"title": title or "Untitled Document"},
            headers={"Authorization": f"Bearer {token}"},
        )
        return resp

    async def get_document(self, document_id: str) -> dict:
        """获取文档信息"""
        token = await self._get_tenant_token()
        resp = await self._get(
            f"https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        return resp

    async def list_document_blocks(self, document_id: str) -> dict:
        """列出文档块"""
        token = await self._get_tenant_token()
        resp = await self._get(
            f"https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/blocks",
            headers={"Authorization": f"Bearer {token}"},
        )
        return resp

    async def create_document_block_children(
        self, document_id: str, block_id: str, children: list
    ) -> dict:
        """创建文档块（追加内容）"""
        token = await self._get_tenant_token()
        resp = await self._post(
            f"https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/children",
            json={"children": children},
            headers={"Authorization": f"Bearer {token}"},
        )
        return resp

    async def update_document_block(
        self, document_id: str, block_id: str, update_text: str
    ) -> dict:
        """更新文档块"""
        token = await self._get_tenant_token()
        resp = await self._patch(
            f"https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}",
            json={"update_text": update_text},
            headers={"Authorization": f"Bearer {token}"},
        )
        return resp

    async def list_files(self, folder_token: str = None, page_size: int = 50) -> dict:
        """列出云盘文件"""
        token = await self._get_tenant_token()
        params = {"page_size": page_size}
        if folder_token:
            params["folder_token"] = folder_token
        resp = await self._get(
            "https://open.feishu.cn/open-apis/drive/v1/files",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        return resp

    async def create_folder(self, name: str, folder_token: str = None) -> dict:
        """创建文件夹"""
        token = await self._get_tenant_token()
        resp = await self._post(
            "https://open.feishu.cn/open-apis/drive/v1/files/create_folder",
            json={"name": name, "folder_token": folder_token or ""},
            headers={"Authorization": f"Bearer {token}"},
        )
        return resp

    async def share_document(
        self, document_id: str, member_type: str, member_id: str, perm: str = "edit"
    ) -> dict:
        """分享文档"""
        token = await self._get_tenant_token()
        resp = await self._post(
            f"https://open.feishu.cn/open-apis/drive/v1/permissions/{document_id}/members/batch_create",
            json={
                "member_type": member_type,
                "member_id": member_id,
                "perm": perm,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        return resp

    async def search_wiki(self, query: str, count: int = 10) -> dict:
        """搜索知识库（需要用户授权）"""
        user_token = self.get_user_access_token()
        if not user_token:
            return {
                "code": 1,
                "msg": "User access token not found. Please authorize first.",
            }
        resp = await self._post(
            "https://open.feishu.cn/open-apis/wiki/v2/nodes/search",
            json={"query": query, "count": count},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        return resp


class FeishuWebhookHandler:
    """飞书 Webhook 处理器"""

    def __init__(self, adapter: FeishuAdapter):
        self.adapter = adapter

    async def handle(self, body: dict, headers: dict):
        return {"code": 0}


_feishu_adapter: Optional[FeishuAdapter] = None
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
