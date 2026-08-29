# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
# cli.py
"""FastClaw 命令行界面"""

import asyncio
import logging
import shutil
import sys
import uuid
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message=".*pkg_resources.*")

try:
    from termcolor import colored
except ImportError:

    def colored(text, color=None):
        return text


from fastmind import Event

if __package__ in (None, ""):
    from core.app import load_settings, start
    from gateway.channels.handlers import (
        handle_channel_command,
        load_sessions,
        save_sessions,
        get_last_session,
    )
else:
    from .core.app import load_settings, start
    from .gateway.channels.handlers import (
        handle_channel_command,
        load_sessions,
        save_sessions,
        get_last_session,
    )

logging.disable(logging.WARNING)


def create_cli_session():
    """创建 CLI 会话并保存到 sessions.json

    绑定 settings.json 的 default_agent_id，而不是硬编码 main_agent。
    """
    sessions = load_sessions()
    new_session_id = f"cli_{uuid.uuid4().hex[:8]}"
    agent_id = load_settings().get("default_agent_id", "main_agent")
    sessions[new_session_id] = {
        "session_id": new_session_id,
        "agent_id": agent_id,
        "created_at": str(uuid.uuid4()),
        "last_active_time": int(__import__("time").time()),
    }
    save_sessions(sessions)
    return new_session_id


def handle_cli_command(
    text: str, current_session_id: str
) -> tuple[bool, str]:
    """处理 CLI 命令，返回 (是否已处理, 新的session_id)"""
    text = text.strip()
    new_session_id = current_session_id

    if text == "/new":
        new_session_id = create_cli_session()
        print(f"\nNew session created: {new_session_id}")
        return True, new_session_id

    elif text == "/clear":
        from fastclaw.core.config import get_sessions_dir

        session_dir = get_sessions_dir() / current_session_id
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
        sessions = load_sessions()
        sessions.pop(current_session_id, None)
        save_sessions(sessions)
        new_session_id = create_cli_session()
        print(f"\nCleared chat history, new session: {new_session_id}")
        return True, new_session_id

    elif text.startswith("/session "):
        parts = text.split(" ", 1)
        if len(parts) == 2:
            target_id = parts[1].strip()
            sessions = load_sessions()
            if target_id in sessions:
                print(f"\nSwitched to session: {target_id}")
                new_session_id = target_id
            else:
                print(f"\nSession not found: {target_id}")
            return True, current_session_id

    elif text == "/session_list":
        sessions = load_sessions()
        if sessions:
            print("\nAll sessions:")
            for sid, info in sessions.items():
                marker = " <-- current" if sid == current_session_id else ""
                agent = info.get("agent_id", "unknown")
                print(f"  - {sid} (agent: {agent}){marker}")
        else:
            print("\nNo active sessions")
        return True, current_session_id

    return False, current_session_id


async def chat(new_session=False, session_id=None):
    """交互式对话"""
    api = await start()
    if session_id:
        pass
    elif new_session:
        session_id = create_cli_session()
    else:
        last_session = get_last_session("cli")
        if last_session:
            session_id = last_session
        else:
            session_id = create_cli_session()

    print("=" * 50)
    print("FastClaw CLI (type 'quit' to exit)")
    print("Commands: /new, /clear, /session <id>, /session_list")
    print("=" * 50)

    async def consume_stream():
        """消费流式输出事件

        thinking 内容实时展示（灰色），正文/工具调用开始时换行分隔。
        """
        buffer = ""
        thinking_started = False

        def _print_safe(text):
            try:
                print(text, end="", flush=True)
            except (UnicodeEncodeError, UnicodeDecodeError):
                safe = text.encode("utf-8", errors="replace").decode(
                    "utf-8", errors="replace"
                )
                print(safe, end="", flush=True)

        def _end_thinking():
            """thinking 段结束：换行分隔正文"""
            nonlocal thinking_started
            if thinking_started:
                thinking_started = False
                print("\n", end="", flush=True)

        try:
            async for event in api.stream_events(session_id):
                if event.type == "stream.thinking":
                    delta = event.payload.get("delta", "")
                    if not thinking_started:
                        thinking_started = True
                        print(f"\n{colored('💭 Thinking:', 'cyan')}", end="", flush=True)
                    _print_safe(colored(delta, "grey"))
                elif event.type == "stream.chunk":
                    _end_thinking()
                    delta = event.payload.get("delta", "")
                    buffer += delta
                    _print_safe(delta)
                elif event.type == "stream.fragment":
                    _end_thinking()
                    tool_calls = event.payload.get("tool_calls", [])
                    if tool_calls:
                        seen = set()
                        unique_names = []
                        for tc in tool_calls:
                            name = tc.get("function", {}).get("name", "unknown")
                            if name not in seen:
                                seen.add(name)
                                unique_names.append(name)
                        print(f"[Executing tool: {', '.join(unique_names)}]")
                    content = event.payload.get("content", "")
                    if content:
                        pass
                elif event.type == "stream.end":
                    _end_thinking()
                    print()
                    return buffer
                elif event.type == "stream.error":
                    _end_thinking()
                    print(f"\n[Error: {event.payload.get('error', 'Unknown error')}]")
                    return None
        except asyncio.CancelledError:
            return buffer
        except Exception as e:
            print(f"\n[Error: {e}]")
            return buffer

    while True:
        try:
            user_input = input("\n\033[38;5;208mYou:\033[0m ").strip()
            if not user_input:
                continue
            if user_input.lower() == "quit":
                break

            is_command, new_session_id = handle_cli_command(
                user_input, session_id
            )
            session_id = new_session_id
            if is_command:
                continue

            print(f"\033[F\033[K\033[38;5;208mYou: {user_input}\033[0m")

            event = Event("user.message", {"text": user_input}, session_id)
            await api.push_event(session_id, event)

            await consume_stream()

        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except EOFError:
            print("\n\nExiting...")
            break
        except Exception as e:
            print(f"\nError: {e}")

    try:
        await api.stop()
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(chat())
