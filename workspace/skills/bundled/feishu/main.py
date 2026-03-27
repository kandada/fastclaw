import json
import httpx
from pathlib import Path


async def execute(
    action: str = None, message: str = None, session_id: str = None, **kwargs
) -> str:
    """飞书技能

    Args:
        action: 操作类型 ("send" | "receive")
        message: 消息内容
        session_id: 飞书用户ID
    """
    config_path = Path("workspace/data/channels/feishu_config.json")
    if not config_path.exists():
        return "Error: Feishu config not found. Please configure feishu first."

    try:
        config = json.loads(config_path.read_text())
    except Exception as e:
        return f"Error: Failed to load config: {str(e)}"

    app_id = config.get("app_id")
    app_secret = config.get("app_secret")

    if not app_id or not app_secret:
        return "Error: Feishu app_id or app_secret not configured"

    if action == "send" and message:
        return await send_feishu_message(app_id, app_secret, message, session_id)
    elif action == "receive":
        return "Feishu receive functionality - use webhook integration"
    else:
        return "Error: Invalid action. Use 'send' or 'receive'."


async def send_feishu_message(
    app_id: str, app_secret: str, message: str, session_id: str = None
) -> str:
    """发送飞书消息"""
    if not session_id:
        return "Error: session_id is required for sending messages"

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
        )
        token_data = token_resp.json()
        if token_data.get("code") != 0:
            return f"Error: Failed to get token: {token_data}"

        tenant_token = token_data.get("tenant_access_token")

        headers = {
            "Authorization": f"Bearer {tenant_token}",
            "Content-Type": "application/json",
        }

        msg_resp = await client.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            headers=headers,
            json={
                "receive_id": session_id,
                "msg_type": "text",
                "content": json.dumps({"text": message}),
            },
            params={"receive_id_type": "open_id"},
        )

        result = msg_resp.json()
        if result.get("code") != 0:
            return f"Error: Failed to send message: {result}"

        return f"Message sent successfully to {session_id}"
