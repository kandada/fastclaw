"""FastClaw 统一入口"""

import asyncio
import argparse
import json
import os
import signal
import sys
import urllib.request
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
    from core.app import start
    from gateway.server import GatewayServer
    from cli import chat as cli_chat
else:
    from .core.app import start
    from .gateway.server import GatewayServer
    from .cli import chat as cli_chat

PID_FILE = "/tmp/fastclaw.pid"
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


def setup_signal_handlers():
    """设置信号处理器"""

    def handler(signum, frame):
        cleanup_pid_file()
        print("\nShutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def status():
    """查看运行状态"""
    try:
        data = api_get("/api/health")
        print(f"Status: {data.get('status', 'unknown')}")
    except Exception as e:
        print(f"Status: offline (server not running)")
    print(f"Server: http://localhost:8765")


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
    print("""FastClaw CLI

Usage: python3 main.py <command> [options]

Commands:
  start                       Start web server (default)
  status                      Show running status
  chat                        Interactive chat mode
  chat --new                  New session chat
  chat --session-id <id>      Continue session chat

  session list                List all sessions
  session history <id>        Show session history
  session clear <id>          Clear session messages
  session export <id>         Export session

  cron list                   List all cron tasks
  cron add                    Add cron task (via API)
  cron del <name>             Delete cron task (via API)
  cron run <name>             Trigger cron task (via API)

  skill list                  List all skills
  skill info <name>           Show skill details
  skill test <name>           Test skill

    agent list                  List all agents
    agent add                   Add new agent (interactive)
    agent info <name>           Show agent details

  help                        Show this help message

Examples:
  python3 main.py start                  # Start server
  python3 main.py status                 # Check status
  python3 main.py chat                  # Interactive chat
  python3 main.py session list           # List sessions
  python3 main.py cron list             # List cron tasks
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
            print("Use 'session list' or 'session history <id>'")
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
        else:
            print(f"Unknown subcommand: {sub}")
            print("Use 'skill list'")
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

        port = 8765
        host = "0.0.0.0"
        for i, arg in enumerate(raw_args):
            if arg == "--port" and i + 1 < len(raw_args):
                port = int(raw_args[i + 1])
            elif arg == "--host" and i + 1 < len(raw_args):
                host = raw_args[i + 1]

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
        setup_signal_handlers()

        print("Starting FastClaw...")

        server = GatewayServer(host=host, port=port)
        await server.start()

        print(f"FastClaw Gateway running at http://{host}:{port}")
        print(f"WebUI available at http://{host}:{port}/")
        print(f"SSE endpoint at http://{host}:{port}/api/chat/{{session_id}}")
        print(f"WebSocket available at ws://{host}:{port}/ws (legacy)")
        print(f"Press Ctrl+C to stop")

        server.run()

        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            cleanup_pid_file()
            print("\nShutting down...")
            await server.stop()
            print("FastClaw stopped")

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
            while True:
                await asyncio.sleep(1)
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
