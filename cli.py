# cli.py
"""FastClaw 命令行界面"""

import asyncio
import sys
import logging
from pathlib import Path

try:
    from termcolor import colored
except ImportError:

    def colored(text, color=None):
        return text

# sys.path.insert(0, str(Path(__file__).parent / "vendor"))

from fastmind import Event
from core.app import start

logging.disable(logging.WARNING)


async def chat(new_session=False, session_id=None):
    """交互式对话"""
    api = await start()
    if session_id:
        pass
    elif new_session:
        import uuid

        session_id = f"cli_{uuid.uuid4().hex[:8]}"
    else:
        session_id = "cli_default_0327_2"

    print("=" * 50)
    print("FastClaw CLI (输入 'quit' 退出)")
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
                        # print(content, end="", flush=True)
                        # buffer += content
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

    while True:
        try:
            user_input = input("\n你: ").strip()
            if not user_input:
                continue
            if user_input.lower() == "quit":
                break

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
