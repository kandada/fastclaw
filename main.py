"""FastClaw 统一入口"""

import asyncio
import argparse
import json
import os
import signal
import sys
import tempfile
import urllib.request
import warnings
from pathlib import Path

# 设置 sys.path 使 fastclaw.* 导入在直接运行模式下也能工作
_main_file = Path(__file__).resolve()
_pkg_dir = _main_file.parent  # fastclaw/
_project_root = _pkg_dir.parent  # fastclaw_local/

# 确保 fastclaw/ 在 sys.path 中（用于 fastclaw.core.config 等导入）
_pkg_dir_str = str(_pkg_dir)
if _pkg_dir_str not in sys.path:
    sys.path.insert(0, _pkg_dir_str)

# 确保项目根目录在 sys.path 中（用于 core.*, gateway.* 等导入）
_root_str = str(_project_root)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)

# 设置默认 FASTCLAW_WORKSPACE 环境变量
_default_ws = _project_root / "workspace"
if os.environ.get("FASTCLAW_WORKSPACE") is None:
    if _default_ws.exists() and _default_ws.is_dir():
        os.environ["FASTCLAW_WORKSPACE"] = str(_default_ws)
    else:
        os.environ["FASTCLAW_WORKSPACE"] = str(Path.home() / ".fastclaw" / "workspace")

if __package__ in (None, ""):
    warnings.filterwarnings("ignore", message=".*pkg_resources.*")
    from core.app import start
    from gateway.server import GatewayServer
    from cli import chat as cli_chat
    from core.bootstrap import copy_seed_files
    from core.config import ensure_settings
else:
    warnings.filterwarnings("ignore", message=".*pkg_resources.*")
    from .core.app import start
    from .gateway.server import GatewayServer
    from .cli import chat as cli_chat
    from .core.bootstrap import copy_seed_files
    from .core.config import ensure_settings

PID_FILE = str(Path(tempfile.gettempdir()) / "fastclaw.pid")
_http_opener = None


def get_http_opener():
    """获取共享的 HTTP opener（带连接池）"""
    global _http_opener
    if _http_opener is None:
        _http_opener = urllib.request.build_opener()
        _http_opener.addheaders = [("User-Agent", "FastClaw-CLI/1.0")]
    return _http_opener


def api_get(path):
    """使用共享连接获取 API 数据"""
    opener = get_http_opener()
    req = urllib.request.Request(f"http://localhost:8765{path}")
    with opener.open(req, timeout=3) as resp:
        return json.loads(resp.read())


def check_pid_file():
    """检查 PID 文件，防止重复启动"""
    if Path(PID_FILE).exists():
        try:
            old_pid = int(Path(PID_FILE).read_text().strip())
            if old_pid != os.getpid():
                try:
                    os.kill(old_pid, 0)
                    print(f"FastClaw is already running! (PID: {old_pid})")
                    print(
                        f"Run 'kill {old_pid}' to stop it first, or delete {PID_FILE}"
                    )
                    sys.exit(1)
                except OSError:
                    pass
        except (ValueError, OSError):
            pass
    Path(PID_FILE).write_text(str(os.getpid()))


def cleanup_pid_file():
    """清理 PID 文件"""
    if Path(PID_FILE).exists():
        try:
            if int(Path(PID_FILE).read_text().strip()) == os.getpid():
                Path(PID_FILE).unlink()
        except (ValueError, OSError):
            pass



def status():
    """查看运行状态"""
    try:
        data = api_get("/api/health")
        print(f"Status: {data.get('status', 'unknown')}")
        print(f"Server: http://localhost:8765")
    except Exception as e:
        print(f"Status: offline (server not running)")


def list_sessions():
    """列出所有会话"""
    try:
        sessions = api_get("/api/sessions")
        if isinstance(sessions, list):
            for s in sessions:
                name = s.get("name", "unnamed")
                sid = s.get("session_id", "unknown")
                last = s.get("last_active_time", 0)
                print(f"  {sid} ({name}) - last active: {last}")
        else:
            print("No sessions found")
    except Exception as e:
        print(f"Error: {e}")


def list_crons():
    """列出所有定时任务"""
    try:
        data = api_get("/api/crons")
        tasks = data.get("tasks", [])
        if tasks:
            for t in tasks:
                name = t.get("name", "unnamed")
                sid = t.get("id", "unknown")
                enabled = t.get("enabled", False)
                schedule = t.get("schedule", "")
                print(f"  [{enabled and 'x' or ' '}] {sid}: {name} ({schedule})")
        else:
            print("No cron tasks found")
    except Exception as e:
        print(f"Error: {e}")


def list_skills():
    """列出所有技能"""
    try:
        data = api_get("/api/skills")
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error: {e}")


def skills_sync():
    """从包内置种子复制缺失的 workspace 文件"""
    ws_path_str = os.environ.get("FASTCLAW_WORKSPACE")
    if not ws_path_str:
        print("Error: FASTCLAW_WORKSPACE not set")
        return
    ws_path = Path(ws_path_str)
    if not ws_path.is_dir():
        print(f"Workspace not found: {ws_path}")
        reply = input("Create it now? [Y/n]: ").strip().lower()
        if reply not in ("", "y", "yes"):
            print("Aborted")
            return
        ws_path.mkdir(parents=True, exist_ok=True)

    copy_seed_files(ws_path)


def list_agents():
    """列出所有Agent"""
    try:
        data = api_get("/api/agents")
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error: {e}")


def input_with_default(prompt, default):
    """交互式输入，支持默认值"""
    val = input(f"{prompt} [{default}]: ").strip()
    return val if val else default


def add_agent():
    """交互式创建新 Agent"""
    print("\n=== Add New Agent ===\n")

    name = input_with_default("Agent name", "my_agent")
    description = input_with_default("Description", "My custom agent")

    print("\nLLM Configuration:")
    provider = input_with_default("Provider (deepseek/openai)", "deepseek")
    api_key = input("API Key: ").strip()
    if not api_key:
        print("Error: API Key is required")
        return

    model = input_with_default("Model", "deepseek-chat")
    base_url = input_with_default("Base URL", "https://api.deepseek.com/v1")

    print("\nContext Configuration:")
    max_tokens = input_with_default("Max tokens", "80000")
    unload_threshold = input_with_default("Unload threshold", "80000")

    agent_config = {
        "name": name,
        "description": description,
        "llm": {
            "gateway": "openai",
            "provider": provider,
            "model": model,
            "api_key": api_key,
            "base_url": base_url,
            "multimodal": False,
        },
        "context": {
            "max_tokens": int(max_tokens),
            "unload_threshold_tokens": int(unload_threshold),
        },
        "extra_workspaces": [],
    }

    from fastclaw.core.config import get_agents_dir

    agents_dir = get_agents_dir()
    agents_dir.mkdir(parents=True, exist_ok=True)

    agent_dir = agents_dir / name
    agent_dir.mkdir(parents=True, exist_ok=True)

    agent_file = agent_dir / "metadata.json"
    with open(agent_file, "w", encoding="utf-8") as f:
        json.dump(agent_config, f, indent=2, ensure_ascii=False)

    print(f"\nAgent '{name}' created at: {agent_file}")
    print(
        "\nNote: To use this agent, restart the FastClaw server or set it as default in WebUI Settings."
    )


def show_help():
    """显示帮助"""
    cmd_name = os.path.basename(sys.argv[0]) if sys.argv[0] else "fastclaw"
    if "__main__" in cmd_name:
        cmd_prefix = "fastclaw" if "fastclaw" in __package__ else "python -m fastclaw"
    elif cmd_name.endswith(".py"):
        cmd_prefix = f"python {cmd_name}"
    else:
        cmd_prefix = cmd_name

    print(f"""FastClaw CLI

Usage: {cmd_prefix} <command> [options]

Commands:
  start                       Start web server (default)
  status                      Show running status
  api                         Start headless API (no web server)
  chat                        Interactive chat mode
  chat --new                  New session chat
  chat --session-id <id>      Continue session chat

  session list                List all sessions

  cron list                   List all cron tasks

  skill list                  List all skills
  skill sync                  Sync workspace seed files

  agent list                  List all agents
  agent add                   Add new agent (interactive)

  help                        Show this help message

Examples:
  {cmd_prefix} start              # Start server
  {cmd_prefix} status             # Check status
  {cmd_prefix} chat               # Interactive chat
  {cmd_prefix} session list       # List sessions
  {cmd_prefix} cron list          # List cron tasks
""")


async def main():
    """主函数"""
    raw_args = sys.argv[1:] if len(sys.argv) > 1 else []
    cmd = raw_args[0] if raw_args else "start"

    if cmd in ("help", "--help", "-h"):
        show_help()
        return
    if cmd == "status":
        status()
        return

    elif cmd == "session":
        sub = raw_args[1] if len(raw_args) > 1 else None
        if sub == "list":
            list_sessions()
        else:
            print(f"Unknown subcommand: {sub}")
            print("Use 'session list'")
        return

    elif cmd == "cron":
        sub = raw_args[1] if len(raw_args) > 1 else None
        if sub == "list":
            list_crons()
        else:
            print(f"Unknown subcommand: {sub}")
            print("Use 'cron list'")
        return

    elif cmd == "skill":
        sub = raw_args[1] if len(raw_args) > 1 else None
        if sub == "list":
            list_skills()
        elif sub == "sync":
            skills_sync()
        else:
            print(f"Unknown subcommand: {sub}")
            print("Use 'skill list' or 'skill sync'")
        return

    elif cmd == "agent":
        sub = raw_args[1] if len(raw_args) > 1 else None
        if sub == "list":
            list_agents()
        elif sub == "add":
            add_agent()
        else:
            print(f"Unknown subcommand: {sub}")
            print("Use 'agent list' or 'agent add'")
        return

    elif cmd == "chat":
        new_session = "--new" in raw_args
        session_id = None
        if "--session-id" in raw_args:
            idx = raw_args.index("--session-id")
            session_id = raw_args[idx + 1] if idx + 1 < len(raw_args) else None

        await cli_chat(new_session=new_session, session_id=session_id)
        return

    elif cmd == "start":
        port = 8765
        host = "0.0.0.0"
        for i, arg in enumerate(raw_args[1:], 1):
            if arg == "--port" and i + 1 < len(raw_args):
                port = int(raw_args[i + 1])
            elif arg == "--host" and i + 1 < len(raw_args):
                host = raw_args[i + 1]

        check_pid_file()

        ws_path_str = os.environ.get("FASTCLAW_WORKSPACE")
        if ws_path_str:
            ws_path = Path(ws_path_str)

            # ---- Workspace 初始化 ----
            # 从 pip 包内置种子复制 workspace 文件。
            # 文件级保护：已有文件跳过，绝不覆盖用户数据。
            # 种子包含: skills/, agents/, settings.json, channels/, cron/
            ws_path.mkdir(parents=True, exist_ok=True)
            copy_seed_files(ws_path)

            # 硬编码兜底：settings.json 仍不存在时用默认值创建
            ensure_settings()

        print("Starting FastClaw...")

        server = GatewayServer(host=host, port=port)
        await server.start()

        print(f"FastClaw Gateway running at http://{host}:{port}")
        print(f"WebUI available at http://{host}:{port}/")
        print(f"SSE endpoint at http://{host}:{port}/api/chat/{{session_id}}")
        print(f"WebSocket available at ws://{host}:{port}/ws (legacy)")
        print(f"Press Ctrl+C to stop")

        _shutdown_count = 0

        def _handle_shutdown_signal(sig, _frame):
            nonlocal _shutdown_count
            _shutdown_count += 1

            srv = server._uvicorn_server
            if srv is not None:
                srv.should_exit = True
                srv.force_exit = True
            if _shutdown_count >= 2:
                os._exit(0)

        prev_sigint = signal.signal(signal.SIGINT, _handle_shutdown_signal)
        prev_sigterm = signal.signal(signal.SIGTERM, _handle_shutdown_signal)

        try:
            await server.run_async()
        except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
            pass

        try:
            cleanup_pid_file()
            print("\nShutting down...")
            try:
                await asyncio.wait_for(server.stop(force=_shutdown_count > 0), timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError, KeyboardInterrupt):
                print("Shutdown interrupted, forcing exit")
        finally:
            print("FastClaw stopped")
            signal.signal(signal.SIGINT, prev_sigint)
            signal.signal(signal.SIGTERM, prev_sigterm)

    elif cmd == "api":
        port = 8765
        host = "0.0.0.0"
        for i, arg in enumerate(raw_args[1:], 1):
            if arg == "--port" and i + 1 < len(raw_args):
                port = int(raw_args[i + 1])
            elif arg == "--host" and i + 1 < len(raw_args):
                host = raw_args[i + 1]

        api = await start()
        print(f"FastClaw API running at http://{host}:{port}")
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            await api.stop()

    else:
        print(f"Unknown command: {cmd}")
        print(
            "Available commands: start, chat, api, status, session, cron, skill, agent, help"
        )


def cli_main():
    """CLI 入口点，供 console_scripts 使用"""
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
