"""飞书技能 - 调用 FeishuAdapter 操作飞书云文档"""

from typing import Optional

import lark_oapi as lark
from lark_oapi.api.docx.v1.model.update_block_request import UpdateBlockRequest

from gateway.channels.feishu import FeishuAdapter


def get_adapter() -> FeishuAdapter:
    try:
        return FeishuAdapter()
    except Exception as e:
        raise Exception(f"Failed to initialize Feishu adapter: {e}")


async def execute(**kwargs) -> str:
    """飞书技能 - 支持消息发送和文档操作

    Args:
        **kwargs: 技能参数，包含 action 和其他操作参数
    """
    action = kwargs.pop("action", None)
    if not action:
        return "Error: action is required"

    adapter = get_adapter()

    if action == "send":
        return await send_message(adapter, **kwargs)
    elif action == "create_doc":
        return await create_document(adapter, **kwargs)
    elif action == "get_doc":
        return await get_document(adapter, **kwargs)
    elif action == "read_doc":
        return await read_document(adapter, **kwargs)
    elif action == "append_doc":
        return await append_document(adapter, **kwargs)
    elif action == "update_doc":
        return await update_document(adapter, **kwargs)
    elif action == "list_files":
        return await list_files(adapter, **kwargs)
    elif action == "create_folder":
        return await create_folder(adapter, **kwargs)
    elif action == "share_doc":
        return await share_document(adapter, **kwargs)
    elif action == "search_wiki":
        return await search_wiki(adapter, **kwargs)
    elif action == "get_auth_url":
        return get_auth_url(adapter, **kwargs)
    elif action == "exchange_user_token":
        return await exchange_user_token(adapter, **kwargs)
    elif action == "refresh_user_token":
        return await refresh_user_token(adapter)
    elif action == "check_user_token":
        return check_user_token(adapter)
    else:
        return f"Error: Unknown action '{action}'. Available actions: send, create_doc, get_doc, read_doc, append_doc, update_doc, list_files, create_folder, share_doc, search_wiki, get_auth_url, exchange_user_token, refresh_user_token, check_user_token"


async def send_message(
    adapter: FeishuAdapter, message: str = None, session_id: str = None, **kwargs
) -> str:
    """发送飞书消息"""
    if not message:
        return "Error: message is required"
    if not session_id:
        return "Error: session_id is required"

    try:
        result = await adapter.send_message(message, open_id=session_id)
        return f"Message sent successfully to {session_id}"
    except Exception as e:
        return f"Error: Failed to send message - {str(e)}"


async def create_document(adapter: FeishuAdapter, title: str = None, **kwargs) -> str:
    """创建飞书云文档"""
    try:
        resp = await adapter.create_document(title)
        if resp.get("code") != 0:
            return f"Error: Failed to create document - {resp.get('msg')}"

        data = resp.get("data", {})
        doc = data.get("document", {})
        return (
            f"Document created successfully:\n"
            f"- Title: {doc.get('title')}\n"
            f"- Document ID (token): {doc.get('document_id')}"
        )
    except Exception as e:
        return f"Error: {str(e)}"


async def get_document(
    adapter: FeishuAdapter, document_id: str = None, **kwargs
) -> str:
    """获取飞书云文档信息"""
    if not document_id:
        return "Error: document_id is required"

    try:
        resp = await adapter.get_document(document_id)
        if resp.get("code") != 0:
            return f"Error: Failed to get document - {resp.get('msg')}"

        data = resp.get("data", {})
        doc = data.get("document", {})
        return (
            f"Document info:\n"
            f"- Title: {doc.get('title')}\n"
            f"- Document ID: {doc.get('document_id')}\n"
            f"- Revision ID: {doc.get('revision_id')}"
        )
    except Exception as e:
        return f"Error: {str(e)}"


async def read_document(
    adapter: FeishuAdapter, document_id: str = None, **kwargs
) -> str:
    """读取飞书云文档内容"""
    if not document_id:
        return "Error: document_id is required"

    try:
        resp = await adapter.list_document_blocks(document_id)
        if resp.get("code") != 0:
            return f"Error: Failed to read document - {resp.get('msg')}"

        data = resp.get("data", {})
        items = data.get("items", [])
        if not items:
            return "Document is empty"

        result = f"Document content (total {len(items)} blocks):\n\n"
        for block in items:
            block_type = block.get("block_type")
            block_id = block.get("block_id")

            if block_type == 1:
                result += f"[Page]\n"
            elif block_type == 2:
                text = _extract_text_from_text_block(block)
                if text:
                    result += f"{text}\n"
            elif block_type == 3:
                result += "[Heading 1]\n"
            elif block_type == 4:
                result += "[Heading 2]\n"
            elif block_type == 5:
                result += "[Heading 3]\n"
            elif block_type == 7:
                result += "[Code Block]\n"
            elif block_type == 13:
                result += "[Quote]\n"
            elif block_type == 15:
                result += "[Divider]\n"
            elif block_type == 17:
                result += "[Table]\n"
            elif block_type == 18:
                result += "[Todo]\n"
            elif block_type == 20:
                result += "[Bullet]\n"
            else:
                result += f"[Block type: {block_type}] (id: {block_id})\n"

        return result
    except Exception as e:
        return f"Error: {str(e)}"


def _extract_text_from_text_block(block: dict) -> str:
    """从文本块中提取文本内容"""
    try:
        text = block.get("text", {})
        elements = text.get("elements", [])
        if elements:
            parts = []
            for elem in elements:
                text_run = elem.get("text_run", {})
                content = text_run.get("content", "")
                if content:
                    parts.append(content)
            return "".join(parts)
    except:
        pass
    return ""


async def append_document(
    adapter: FeishuAdapter,
    document_id: str = None,
    block_id: str = None,
    content: str = None,
    block_type: int = 2,
    **kwargs,
) -> str:
    """追加内容到飞书云文档"""
    if not document_id:
        return "Error: document_id is required"
    if not content:
        return "Error: content is required"

    if block_id is None:
        block_id = document_id

    text_elements = [{"text_run": {"content": content}}]

    children = [{"block_type": block_type, "text": {"elements": text_elements}}]

    try:
        resp = await adapter.create_document_block_children(
            document_id, block_id, children
        )
        if resp.get("code") != 0:
            return f"Error: Failed to append content - {resp.get('msg')}"

        data = resp.get("data", {})
        children_result = data.get("children", [])
        if children_result:
            first_child = children_result[0]
            return f"Content appended successfully. New block ID: {first_child.get('block_id')}"
        return "Content appended successfully"
    except Exception as e:
        return f"Error: {str(e)}"


async def update_document(
    adapter: FeishuAdapter,
    document_id: str = None,
    block_id: str = None,
    content: str = None,
    **kwargs,
) -> str:
    """更新飞书云文档中的块内容"""
    if not document_id:
        return "Error: document_id is required"
    if not block_id:
        return "Error: block_id is required"
    if not content:
        return "Error: content is required"

    text_elements = [{"text_run": {"content": content}}]
    update_text = {"elements": text_elements}

    try:
        resp = await adapter._patch(
            f"https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}",
            json={"update_text": update_text},
            headers={"Authorization": f"Bearer {await adapter._get_tenant_token()}"},
        )
        if resp.get("code") != 0:
            return f"Error: Failed to update block - {resp.get('msg')}"
        return f"Block {block_id} updated successfully"
    except Exception as e:
        return f"Error: {str(e)}"


async def list_files(
    adapter: FeishuAdapter, folder_token: str = None, page_size: int = 50, **kwargs
) -> str:
    """列出飞书云盘文件"""
    try:
        resp = await adapter.list_files(folder_token, page_size)
        if resp.get("code") != 0:
            return f"Error: Failed to list files - {resp.get('msg')}"

        data = resp.get("data", {})
        files = data.get("files", [])
        if not files:
            return "No files found"

        result = f"Files (total {len(files)}):\n\n"
        for f in files:
            file_type = f.get("type", "unknown")
            name = f.get("name", "unnamed")
            token = f.get("token", "")
            result += f"- [{file_type}] {name} (token: {token})\n"

        return result
    except Exception as e:
        return f"Error: {str(e)}"


async def create_folder(
    adapter: FeishuAdapter, name: str = None, folder_token: str = None, **kwargs
) -> str:
    """创建飞书云盘文件夹"""
    if not name:
        return "Error: folder name is required"

    try:
        resp = await adapter.create_folder(name, folder_token)
        if resp.get("code") != 0:
            return f"Error: Failed to create folder - {resp.get('msg')}"

        data = resp.get("data", {})
        file = data.get("file", {})
        return (
            f"Folder created successfully:\n"
            f"- Name: {file.get('name')}\n"
            f"- Token: {file.get('token')}"
        )
    except Exception as e:
        return f"Error: {str(e)}"


async def share_document(
    adapter: FeishuAdapter,
    document_id: str = None,
    member_type: str = "openid",
    member_id: str = None,
    share_type: str = "edit",
    **kwargs,
) -> str:
    """分享飞书云文档"""
    if not document_id:
        return "Error: document_id is required"
    if not member_id:
        return "Error: member_id is required"

    try:
        resp = await adapter.share_document(
            document_id, member_type, member_id, share_type
        )
        if resp.get("code") != 0:
            return f"Error: Failed to share document - {resp.get('msg')}"
        return (
            f"Document shared successfully with {member_id} ({share_type} permission)"
        )
    except Exception as e:
        return f"Error: {str(e)}"


async def search_wiki(
    adapter: FeishuAdapter, query: str = None, count: int = 10, **kwargs
) -> str:
    """搜索飞书知识库（需要用户授权）"""
    if not query:
        return "Error: query is required"

    try:
        resp = await adapter.search_wiki(query, count)
        if resp.get("code") != 0:
            return f"Error: {resp.get('msg')}"

        data = resp.get("data", {})
        nodes = data.get("items", [])
        if not nodes:
            return f"No wiki nodes found for query: {query}"

        result = f"Wiki search results for '{query}' (total {len(nodes)}):\n\n"
        for node in nodes:
            title = node.get("title", "untitled")
            token = node.get("obj_token", "")
            url = node.get("url", "")
            result += f"- {title}\n  Token: {token}\n  URL: {url}\n\n"

        return result
    except Exception as e:
        return f"Error: {str(e)}"


def get_auth_url(adapter: FeishuAdapter, redirect_uri: str = None, **kwargs) -> str:
    """获取OAuth授权URL"""
    url = adapter.get_auth_url(redirect_uri)
    return (
        f"请访问以下URL进行授权：\n\n{url}\n\n"
        "授权后，将获取到的授权码(code)用于 exchange_user_token 操作"
    )


async def exchange_user_token(
    adapter: FeishuAdapter, code: str = None, **kwargs
) -> str:
    """交换授权码获取用户Token"""
    if not code:
        return "Error: code is required (授权后获取的授权码)"

    try:
        resp = await adapter.exchange_user_token(code)
        if resp.get("code") != 0:
            return f"Error: Failed to exchange token - {resp.get('msg')}"

        data = resp.get("data", {})
        access_token = data.get("access_token", "")
        refresh_token = data.get("refresh_token", "")
        expires_in = data.get("expires_in", 0)

        return (
            f"User access token obtained successfully!\n\n"
            f"Access token: {access_token[:20]}...\n"
            f"Refresh token: {refresh_token[:20]}...\n"
            f"Expires in: {expires_in} seconds"
        )
    except Exception as e:
        return f"Error: {str(e)}"


async def refresh_user_token(adapter: FeishuAdapter) -> str:
    """刷新用户Token"""
    try:
        resp = await adapter.refresh_user_token()
        if resp.get("code") != 0:
            return f"Error: Failed to refresh token - {resp.get('msg')}"

        data = resp.get("data", {})
        access_token = data.get("access_token", "")
        expires_in = data.get("expires_in", 0)

        return (
            f"User access token refreshed successfully!\n\n"
            f"Access token: {access_token[:20]}...\n"
            f"Expires in: {expires_in} seconds"
        )
    except Exception as e:
        return f"Error: {str(e)}"


def check_user_token(adapter: FeishuAdapter) -> str:
    """检查用户Token状态"""
    token = adapter.get_user_access_token()
    if token:
        return f"User access token: {token[:20]}...\nWiki search is ready to use."
    return "User access token not set. Please run 'get_auth_url' to get authorization URL, then use 'exchange_user_token' with the code."
