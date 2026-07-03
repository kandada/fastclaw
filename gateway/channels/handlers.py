# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""Channel 消息处理共享逻辑

所有支持流式响应的 channel（飞书、Telegram等）应使用此模块中的
handle_channel_message 函数来处理消息并获取 AI 响应。
"""

import asyncio
import json
import time
import uuid
from typing import Callable, Awaitable, List, Dict, Any, Optional
from fastmind import Event

from fastclaw.core.config import get_sessions_dir, get_session_store

SESSION_DB_FILE = get_session_store().db_file


def load_sessions() -> dict:
    return get_session_store().load()


def save_sessions(sessions: dict):
    get_session_store().save(sessions)


async def _load_sessions_async() -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, load_sessions)


async def _save_sessions_async(sessions: dict):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, save_sessions, sessions)


def get_last_session(channel: str) -> Optional[str]:
    """获取指定渠道最近使用的 session（根据 last_active_time）"""
    sessions = load_sessions()
    prefix = f"{channel}_"

    matching_sessions = [
        (sid, info) for sid, info in sessions.items() if sid.startswith(prefix)
    ]

    if not matching_sessions:
        return None

    matching_sessions.sort(key=lambda x: x[1].get("last_active_time", 0), reverse=True)
    return matching_sessions[0][0]


async def handle_channel_command(
    channel_name: str,
    sender_id: str,
    text_content: str,
    api,
    send_func: Callable[[str, str], Awaitable[dict]],
) -> tuple[bool, Optional[str]]:
    """处理渠道命令

    识别并执行以下命令：
    - /new: 创建新会话
    - /clear: 清空当前会话聊天记录
    - /session <session_id>: 切换到指定会话
    - /session_list: 列出所有会话

    Args:
        channel_name: 渠道名称
        sender_id: 发送者 ID（当前 session_id）
        text_content: 消息文本
        api: FastMindAPI 实例
        send_func: 发送消息的函数

    Returns:
        tuple: (是否处理, 当前应使用的 session_id)
            - is_command: True 表示命令已处理，False 表示未识别命令
            - session_id: 命令执行后应使用的 session_id（用于更新映射）
    """
    text = text_content.strip()

    if text == "/new":
        sessions = await _load_sessions_async()
        new_session_id = f"{channel_name}_{str(uuid.uuid4())[:8]}"
        sessions[new_session_id] = {
            "session_id": new_session_id,
            "agent_id": "main_agent",
            "created_at": str(uuid.uuid4()),
            "last_active_time": int(time.time()),
            "channel": channel_name,
        }
        await _save_sessions_async(sessions)

        reply = f"New session created. ID: {new_session_id}"
        print(f"[{channel_name}] /new -> {new_session_id}")
        await send_func(reply, sender_id)
        return True, new_session_id

    elif text == "/clear":
        from fastclaw.core.config import get_sessions_dir

        session_id = sender_id
        session_dir = get_sessions_dir() / session_id
        messages_file = session_dir / "messages.jsonl"

        if messages_file.exists():
            messages_file.unlink()

        sessions = await _load_sessions_async()
        if session_id in sessions:
            sessions[session_id]["last_active_time"] = int(time.time())
            await _save_sessions_async(sessions)

        reply = f"Cleared chat history for session {session_id}"
        print(f"[{channel_name}] /clear -> {session_id}")
        await send_func(reply, sender_id)
        return True, session_id

    elif text.startswith("/session "):
        parts = text.split(" ", 1)
        if len(parts) == 2:
            target_session_id = parts[1].strip()
            sessions = await _load_sessions_async()

            if target_session_id in sessions:
                reply = f"Switched to session: {target_session_id}"
                print(f"[{channel_name}] /session {target_session_id}")
                await send_func(reply, sender_id)
                return True, target_session_id
            else:
                reply = f"Session not found: {target_session_id}"
                print(f"[{channel_name}] /session {target_session_id} - not found")
                await send_func(reply, sender_id)
                return True, sender_id

    elif text == "/session_list":
        sessions = await _load_sessions_async()
        if sessions:
            lines = ["All sessions:"]
            for sid, info in sessions.items():
                agent = info.get("agent_id", "unknown")
                lines.append(f"- {sid} (agent: {agent})")
            reply = "\n".join(lines)
        else:
            reply = "No active sessions"
        print(f"[{channel_name}] /session_list -> {len(sessions)} sessions")
        await send_func(reply, sender_id)
        return True, sender_id

    return False, sender_id


async def handle_channel_message(
    channel_name: str,
    sender_id: str,
    text_content: str,
    api,
    send_func: Callable[[str, str], Awaitable[dict]],
    timeout: float = 60.0,
    default_reply: str = "Message received",
    include_thinking: bool = True,
    include_tools: bool = True,
) -> tuple[bool, str]:
    """处理 channel 消息并获取 AI 响应

    使用 stream_events 异步迭代获取 AI 的流式响应，这是正确的方式。
    响应按原始流式顺序展示，包含消息内容、思考过程、工具调用信息。

    Returns:
        tuple: (是否成功, 当前应使用的 session_id)
    """
    # (c) 2024-2026 xiefujin <490021684@qq.com> GPLv3
    if not api:
        print(f"[{channel_name}] ERROR: _websocket_api is None!")
        return False, sender_id

    if not text_content or not sender_id:
        print(f"[{channel_name}] Invalid message: empty text or sender_id")
        return False, sender_id

    is_command, session_id = await handle_channel_command(
        channel_name, sender_id, text_content, api, send_func
    )
    if is_command:
        return True, session_id

    sessions = await _load_sessions_async()
    if session_id not in sessions:
        sessions[session_id] = {
            "session_id": session_id,
            "agent_id": "main_agent",
            "created_at": str(uuid.uuid4()),
            "last_active_time": int(time.time()),
            "channel": channel_name,
        }
        await _save_sessions_async(sessions)

    event = Event(
        type="user.message",
        payload={"text": text_content, "channel": channel_name},
        session_id=session_id,
    )

    try:
        await api.push_event(session_id, event)
    except Exception as e:
        print(f"[{channel_name}] push_event failed: {e}")
        await send_func(default_reply, session_id)
        return False, session_id

    output_parts = []
    has_output = False
    current_section = None

    def end_current_section():
        if current_section == "thinking":
            output_parts.append("\n------\n")
        elif current_section == "tool":
            output_parts.append("\n------\n")

    def format_tool_call(tc: Dict[str, Any]) -> str:
        name = tc.get("name", "unknown")
        args = tc.get("args", "")
        args_str = f"({args})" if args else "()"
        return f"{name}{args_str}"

    try:
        async for stream_event in api.stream_events(session_id):
            if stream_event.type == "stream.chunk":
                if current_section is not None:
                    end_current_section()
                    current_section = None
                delta = stream_event.payload.get("delta", "")
                if delta:
                    output_parts.append(delta)
                    has_output = True

            elif stream_event.type == "stream.thinking":
                if include_thinking:
                    delta = stream_event.payload.get("delta", "")
                    if delta:
                        if current_section != "thinking":
                            if current_section is not None:
                                end_current_section()
                            current_section = "thinking"
                            output_parts.append("[Thinking...]\n")
                        output_parts.append(delta)
                        has_output = True

            elif stream_event.type == "stream.fragment":
                if stream_event.payload.get("has_tool_calls"):
                    if include_tools:
                        if current_section is not None:
                            end_current_section()
                        current_section = "tool"
                        output_parts.append("[Tool executing...]\n")
                        calls = stream_event.payload.get("tool_calls", [])
                        for tc in calls:
                            func_name = tc.get("function", {}).get("name", "")
                            args_str = tc.get("function", {}).get("arguments", "")
                            try:
                                args_obj = json.loads(args_str) if args_str else {}
                                if isinstance(args_obj, dict):
                                    first_arg = next(
                                        iter(args_obj.values()),
                                        args_str[:100] if args_str else "",
                                    )
                                else:
                                    first_arg = str(args_obj)[:100] if args_str else ""
                            except:
                                first_arg = args_str[:100] if args_str else ""
                            output_parts.append(
                                format_tool_call(
                                    {
                                        "name": func_name,
                                        "args": first_arg,
                                    }
                                )
                            )
                            has_output = True
                else:
                    if current_section is not None:
                        end_current_section()
                        current_section = None
                    content = stream_event.payload.get("content", "")
                    if content:
                        output_parts.append(content)
                        has_output = True

            elif stream_event.type == "stream.end":
                break

            elif stream_event.type == "stream.error":
                if current_section is not None:
                    end_current_section()
                    current_section = None
                error_msg = stream_event.payload.get("error", "unknown error")
                print(f"[{channel_name}] stream error: {error_msg}")
                break

        if has_output:
            final_reply = "".join(output_parts)
            if final_reply.strip():
                print(f"[{channel_name}] Reply: {final_reply[:50]}...")
                await send_func(final_reply, session_id)
                return True, session_id
            else:
                print(f"[{channel_name}] Empty reply received")
                await send_func(default_reply, session_id)
                return True, session_id
        else:
            print(f"[{channel_name}] No reply from AI")
            await send_func(default_reply, session_id)
            return True, session_id

    except asyncio.TimeoutError:
        print(f"[{channel_name}] Timeout waiting for AI response")
        await send_func(default_reply, session_id)
        return False, session_id

    except Exception as e:
        print(f"[{channel_name}] Error getting AI response: {e}")
        await send_func(default_reply, session_id)
        return False, session_id
