# cli.py
"""FastClaw 命令行界面"""

import asyncio
import sys
import logging
import uuid
from pathlib import Path

try:
    from termcolor import colored
except ImportError:

    def colored(text, color=None):
        return text


from fastmind import Event
from core.app import start
from gateway.channels.handlers import (
    handle_channel_command,
    load_sessions,
    save_sessions,
    get_last_session,
)

logging.disable(logging.WARNING)


def create_cli_session():
    """创建 CLI 会话并保存到 sessions.json"""
    sessions = load_sessions()
    new_session_id = f"cli_{uuid.uuid4().hex[:8]}"
    sessions[new_session_id] = {
        "session_id": new_session_id,
        "agent_id": "main_agent",
        "created_at": str(uuid.uuid4()),
        "last_active_time": int(__import__("time").time()),
    }
    save_sessions(sessions)
    return new_session_id


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
    print("FastClaw CLI (输入 'quit' 退出)")
    print("支持命令: /new, /clear, /session <id>, /session_list")
    print("=" * 50)

    async def consume_stream():
        """消费流式输出事件"""
        buffer = ""
        thinking_buffer = ""
        thinking_shown = False
        try:
            async for event in api.stream_events(session_id):
                if event.type == "stream.thinking":
                    delta = event.payload.get("delta", "")
                    delta_clean = delta.replace("\n", " ").replace("\r", " ")
                    if not thinking_shown:
                        thinking_shown = True
                        thinking_buffer = ""
                        print(f"{colored('[思考中...] ', 'cyan')}", end="", flush=True)
                    thinking_buffer += delta_clean
                    display_text = thinking_buffer[:200]
                    print(
                        f"\r{colored('[思考中...] ', 'cyan')}{display_text}",
                        end="",
                        flush=True,
                    )
                elif event.type == "stream.chunk":
                    if thinking_shown:
                        print("\r" + " " * 80, end="", flush=True)
                        print("\r", end="", flush=True)
                        thinking_shown = False
                        thinking_buffer = ""
                    delta = event.payload.get("delta", "")
                    buffer += delta
                    try:
                        print(delta, end="", flush=True)
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        safe_delta = delta.encode("utf-8", errors="replace").decode(
                            "utf-8", errors="replace"
                        )
                        print(safe_delta, end="", flush=True)
                elif event.type == "stream.fragment":
                    if thinking_shown:
                        print("\r" + " " * 80, end="", flush=True)
                        print("\r", end="", flush=True)
                        thinking_shown = False
                        thinking_buffer = ""
                    tool_calls = event.payload.get("tool_calls", [])
                    if tool_calls:
                        seen = set()
                        unique_names = []
                        for tc in tool_calls:
                            name = tc.get("function", {}).get("name", "unknown")
                            if name not in seen:
                                seen.add(name)
                                unique_names.append(name)
                        print(f"[执行工具: {', '.join(unique_names)}]")
                    content = event.payload.get("content", "")
                    if content:
                        pass
                elif event.type == "stream.end":
                    if thinking_shown:
                        print("\r" + " " * 80, end="", flush=True)
                        print("\r", end="", flush=True)
                        thinking_shown = False
                        thinking_buffer = ""
                    print()
                    return buffer
                elif event.type == "stream.error":
                    if thinking_shown:
                        print("\r" + " " * 80, end="", flush=True)
                        print("\r", end="", flush=True)
                        thinking_shown = False
                        thinking_buffer = ""
                    print(f"\n[错误: {event.payload.get('error', '未知错误')}]")
                    return None
        except asyncio.CancelledError:
            return buffer
        except Exception as e:
            print(f"\n[异常: {e}]")
            return buffer

    async def handle_cli_command(
        text: str, current_session_id: str
    ) -> tuple[bool, str]:
        """处理 CLI 命令，返回 (是否已处理, 是否需要更新session_id, 新的session_id)"""
        text = text.strip()
        new_session_id = current_session_id

        if text == "/new":
            new_session_id = create_cli_session()
            print(f"\n已创建新会话: {new_session_id}")
            return True, new_session_id

        elif text == "/clear":
            session_dir = Path(f"workspace/data/sessions/{current_session_id}")
            messages_file = session_dir / "messages.jsonl"
            if messages_file.exists():
                messages_file.unlink()
            print(f"\n已清空当前会话 {current_session_id} 的聊天记录")
            return True, current_session_id

        elif text.startswith("/session "):
            parts = text.split(" ", 1)
            if len(parts) == 2:
                target_id = parts[1].strip()
                sessions = load_sessions()
                if target_id in sessions:
                    print(f"\n已切换到会话: {target_id}")
                    new_session_id = target_id
                else:
                    print(f"\n未找到会话: {target_id}")
                return True, current_session_id

        elif text == "/session_list":
            sessions = load_sessions()
            if sessions:
                print("\n当前所有会话:")
                for sid, info in sessions.items():
                    marker = " <-- 当前" if sid == current_session_id else ""
                    agent = info.get("agent_id", "unknown")
                    print(f"  - {sid} (agent: {agent}){marker}")
            else:
                print("\n当前没有会话")
            return True, current_session_id

        return False, current_session_id

    while True:
        try:
            user_input = input(f"\n你 ({session_id}): ").strip()
            if not user_input:
                continue
            if user_input.lower() == "quit":
                break

            is_command, new_session_id = await handle_cli_command(
                user_input, session_id
            )
            session_id = new_session_id
            if is_command:
                continue

            event = Event("user.message", {"text": user_input}, session_id)
            await api.push_event(session_id, event)

            await consume_stream()

        except KeyboardInterrupt:
            print("\n\n退出...")
            break
        except EOFError:
            print("\n\n退出...")
            break
        except Exception as e:
            print(f"\n错误: {e}")

    await api.stop()


if __name__ == "__main__":
    asyncio.run(chat())
