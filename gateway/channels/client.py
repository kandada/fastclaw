"""通用 HTTP Client 基类

提供 Token 管理、HTTP 请求、OAuth 流程等通用能力
"""

import json
import time
from pathlib import Path
from typing import Optional, Dict, Any

import httpx


class BaseHttpClient:
    """HTTP Client 基类"""

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self._http_client: Optional[httpx.AsyncClient] = None

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            return {}
        return json.loads(self.config_path.read_text())

    def _save_config(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(self.config, indent=2))

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient()
        return self._http_client

    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def _post(
        self, url: str, json: dict = None, headers: dict = None, **kwargs
    ) -> dict:
        """POST 请求"""
        response = await self.http_client.post(
            url, json=json, headers=headers, **kwargs
        )
        return response.json()

    async def _get(
        self, url: str, params: dict = None, headers: dict = None, **kwargs
    ) -> dict:
        """GET 请求"""
        response = await self.http_client.get(
            url, params=params, headers=headers, **kwargs
        )
        return response.json()

    async def _patch(
        self, url: str, json: dict = None, headers: dict = None, **kwargs
    ) -> dict:
        """PATCH 请求"""
        response = await self.http_client.patch(
            url, json=json, headers=headers, **kwargs
        )
        return response.json()


class TokenManager:
    """Token 管理器"""

    def __init__(self, client: BaseHttpClient, token_type: str = "tenant"):
        self.client = client
        self.token_type = token_type
        self._token_key = f"{token_type}_access_token"
        self._expires_at_key = f"{token_type}_token_expires_at"

    def get_token(self) -> Optional[str]:
        expires_at = self.client.config.get(self._expires_at_key, 0)
        if expires_at and time.time() >= expires_at - 60:
            return None
        return self.client.config.get(self._token_key)

    def set_token(self, token: str, expires_in: int = None):
        self.client.config[self._token_key] = token
        if expires_in:
            self.client.config[self._expires_at_key] = int(time.time()) + expires_in
        self.client._save_config()

    def clear_token(self):
        self.client.config.pop(self._token_key, None)
        self.client.config.pop(self._expires_at_key, None)
        self.client._save_config()


class OAuthHelper:
    """OAuth 辅助类"""

    def __init__(self, client: BaseHttpClient):
        self.client = client

    def get_authorization_url(
        self,
        redirect_uri: str = None,
        scope: str = "wiki:wiki:readonly",
        state: str = "auth",
    ) -> str:
        """生成授权 URL（扫码登录方式）"""
        app_id = self.client.config.get("app_id")
        if not app_id:
            raise ValueError("app_id not configured")
        from urllib.parse import quote

        scope_encoded = quote(scope)
        redirect_uri_encoded = quote(
            "https://open.feishu.cn/connect/qrcode/connect/callback"
        )
        return (
            f"https://open.feishu.cn/connect/qrcode/connect/authorize?"
            f"app_id={app_id}&redirect_uri={redirect_uri_encoded}&scope={scope_encoded}&state={state}"
        )

    async def exchange_code_for_token(self, code: str) -> dict:
        """用授权码换取 user_access_token"""
        app_token = await self._get_app_access_token()
        resp = await self.client._post(
            "https://open.feishu.cn/open-apis/authen/v1/oidc/access_token",
            json={
                "grant_type": "authorization_code",
                "code": code,
                "app_id": self.client.config.get("app_id"),
                "app_secret": self.client.config.get("app_secret"),
            },
            headers={"Authorization": f"Bearer {app_token}"},
        )
        return resp

    async def refresh_user_token(self, refresh_token: str) -> dict:
        """刷新 user_access_token"""
        app_token = await self._get_app_access_token()
        resp = await self.client._post(
            "https://open.feishu.cn/open-apis/authen/v1/oidc/refresh_access_token",
            json={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "app_id": self.client.config.get("app_id"),
                "app_secret": self.client.config.get("app_secret"),
            },
            headers={"Authorization": f"Bearer {app_token}"},
        )
        return resp

    async def _get_app_access_token(self) -> str:
        """获取 app_access_token"""
        resp = await self.client._post(
            "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal",
            json={
                "app_id": self.client.config.get("app_id"),
                "app_secret": self.client.config.get("app_secret"),
            },
        )
        data = resp
        if data.get("code") != 0:
            raise Exception(f"Failed to get app access token: {data}")
        return data.get("app_access_token")
