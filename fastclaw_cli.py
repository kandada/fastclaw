"""FastClaw CLI 命令行工具"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from core.app import SKILLS, load_skills, load_agent_config, load_settings


def cmd_cron_list():
    """列出所有 Cron 任务"""
    tasks_file = Path("workspace/data/cron/tasks.json")
    if not tasks_file.exists():
        print("No cron tasks configured")
        return

    tasks = json.loads(tasks_file.read_text())
    if not tasks:
        print("No cron tasks configured")
        return

    print(f"{'Name':<20} {'Schedule':<15} {'Agent':<15} {'Session':<15} {'Status':<10}")
    print("-" * 80)
    for task in tasks:
        status = "Enabled" if task.get("enabled", False) else "Disabled"
        print(
            f"{task.get('name', ''):<20} {task.get('schedule', ''):<15} {task.get('agent_id', ''):<15} {task.get('session_id', 'auto'):<15} {status:<10}"
        )


def cmd_cron_add():
    """添加 Cron 任务（交互式）"""
    print("Add new Cron Task")
    print("=" * 40)

    name = input("Task name: ").strip()
    if not name:
        print("Name is required")
        return

    schedule = input("Cron expression (分 时 日 月 周, e.g. '0 9 * * *'): ").strip()
    if not schedule:
        print("Schedule is required")
        return

    description = input("Description (optional): ").strip()
    agent_id = input("Agent ID (default: main_agent): ").strip() or "main_agent"
    session_id = input("Session ID (optional, press Enter for auto): ").strip()

    tasks_file = Path("workspace/data/cron/tasks.json")
    tasks_file.parent.mkdir(parents=True, exist_ok=True)

    tasks = []
    if tasks_file.exists():
        try:
            tasks = json.loads(tasks_file.read_text())
        except:
            pass

    task_id = f"task_{int(time.time())}"
    task = {
        "id": task_id,
        "name": name,
        "schedule": schedule,
        "description": description,
        "agent_id": agent_id,
        "session_id": session_id or None,
        "enabled": True,
    }

    tasks.append(task)
    tasks_file.write_text(json.dumps(tasks, indent=2))
    print(f"\nTask '{name}' created successfully (ID: {task_id})")


def cmd_cron_del(task_name: str):
    """删除 Cron 任务"""
    tasks_file = Path("workspace/data/cron/tasks.json")
    if not tasks_file.exists():
        print("No cron tasks configured")
        return

    tasks = json.loads(tasks_file.read_text())
    original_count = len(tasks)
    tasks = [t for t in tasks if t.get("name") != task_name]

    if len(tasks) == original_count:
        print(f"Task '{task_name}' not found")
        return

    tasks_file.write_text(json.dumps(tasks, indent=2))
    print(f"Task '{task_name}' deleted")


def cmd_cron_run(task_name: str):
    """手动触发 Cron 任务"""
    from gateway.router import _websocket_api

    if _websocket_api is None:
        print("Error: API not initialized. Please start the server first.")
        return

    tasks_file = Path("workspace/data/cron/tasks.json")
    if not tasks_file.exists():
        print("No cron tasks configured")
        return

    tasks = json.loads(tasks_file.read_text())
    task = None
    for t in tasks:
        if t.get("name") == task_name:
            task = t
            break

    if not task:
        print(f"Task '{task_name}' not found")
        return

    from fastmind import Event

    session_id = task.get("session_id") or "default"
    event = Event(
        "cron.triggered",
        {
            "task_id": task["id"],
            "task_name": task["name"],
            "description": task.get("description", ""),
            "agent_id": task.get("agent_id", "main_agent"),
            "manual": True,
        },
        session_id,
    )
    asyncio.run(_websocket_api.push_event(session_id, event))
    print(f"Task '{task_name}' triggered in session '{session_id}'")


def cmd_session_list():
    """列出所有会话"""
    sessions_file = Path("workspace/data/sessions/sessions.json")
    if not sessions_file.exists():
        print("No sessions")
        return

    sessions = json.loads(sessions_file.read_text())
    if not sessions:
        print("No sessions")
        return

    print(f"{'Session ID':<12} {'Name':<20} {'Agent':<15} {'Last Active':<20}")
    print("-" * 70)
    for sid, sess in sessions.items():
        last_active = sess.get("last_active_time", 0)
        if last_active:
            last_active = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(last_active)
            )
        else:
            last_active = "Never"
        print(
            f"{sid:<12} {(sess.get('name') or sid):<20} {sess.get('agent_id', ''):<15} {last_active:<20}"
        )


def cmd_session_history(session_id: str):
    """查看会话历史"""
    messages_file = Path(f"workspace/data/sessions/{session_id}/messages.jsonl")
    if not messages_file.exists():
        print(f"Session '{session_id}' not found or has no messages")
        return

    messages = []
    for line in messages_file.read_text().splitlines():
        if line.strip():
            try:
                messages.append(json.loads(line))
            except:
                pass

    if not messages:
        print(f"Session '{session_id}' has no messages")
        return

    print(f"Session '{session_id}' - {len(messages)} messages")
    print("=" * 60)
    for msg in messages[-20:]:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")[:100]
        if role == "tool":
            content = f"[tool: {msg.get('tool_call_id', '')}] {content[:80]}"
        print(f"\n[{role.upper()}]")
        print(content)


def cmd_session_clear(session_id: str):
    """清空会话"""
    messages_file = Path(f"workspace/data/sessions/{session_id}/messages.jsonl")
    if messages_file.exists():
        messages_file.unlink()
        print(f"Session '{session_id}' cleared")
    else:
        print(f"Session '{session_id}' not found")


def cmd_session_export(session_id: str):
    """导出会话"""
    sessions_file = Path("workspace/data/sessions/sessions.json")
    if not sessions_file.exists():
        print(f"Session '{session_id}' not found")
        return

    sessions = json.loads(sessions_file.read_text())
    if session_id not in sessions:
        print(f"Session '{session_id}' not found")
        return

    messages_file = Path(f"workspace/data/sessions/{session_id}/messages.jsonl")
    messages = []
    if messages_file.exists():
        for line in messages_file.read_text().splitlines():
            if line.strip():
                try:
                    messages.append(json.loads(line))
                except:
                    pass

    export_data = {"session": sessions[session_id], "messages": messages}

    export_file = Path(f"workspace/data/sessions/{session_id}_export.json")
    export_file.write_text(json.dumps(export_data, indent=2, ensure_ascii=False))
    print(f"Session exported to {export_file}")


def cmd_skill_list():
    """列出所有技能"""
    skills = load_skills()
    if not skills:
        print("No skills available")
        return

    print(f"{'Skill Name':<25} Description")
    print("-" * 60)
    for name, info in skills.items():
        print(f"{name:<25} {info.get('description', '')}")


def cmd_skill_info(skill_name: str):
    """查看技能详情"""
    skills = load_skills()
    if skill_name not in skills:
        print(f"Skill '{skill_name}' not found")
        return

    skill_info = skills[skill_name]
    skill_md_path = Path(skill_info["path"]) / "SKILL.md"
    if skill_md_path.exists():
        print(skill_md_path.read_text())
    else:
        print(f"Skill: {skill_name}")
        print(f"Description: {skill_info.get('description', '')}")
        print(f"Path: {skill_info['path']}")


def cmd_skill_test(skill_name: str):
    """测试技能"""
    from core.app import execute_skill

    print(f"Testing skill '{skill_name}'...")
    result = asyncio.run(execute_skill(skill_name))
    print(result)


def cmd_agent_list():
    """列出所有 Agent"""
    agents_dir = Path("workspace/data/agents")
    if not agents_dir.exists():
        print("No agents configured")
        return

    agents = []
    for agent_path in agents_dir.iterdir():
        if agent_path.is_dir():
            metadata_file = agent_path / "metadata.json"
            if metadata_file.exists():
                try:
                    agents.append(json.loads(metadata_file.read_text()))
                except:
                    pass

    if not agents:
        print("No agents configured")
        return

    print(f"{'Agent ID':<20} LLM Model")
    print("-" * 50)
    for agent in agents:
        llm = agent.get("llm", {})
        model = llm.get("model", "N/A")
        print(f"{agent.get('name', ''):<20} {model}")


def cmd_agent_info(agent_name: str):
    """查看 Agent 配置"""
    config = load_agent_config(agent_name)
    print(json.dumps(config, indent=2))


def cmd_agent_add():
    """添加新 Agent（交互式）"""
    print("Add new Agent")
    print("=" * 40)

    agent_id = input("Agent ID: ").strip()
    if not agent_id:
        print("Agent ID is required")
        return

    agent_dir = Path(f"workspace/data/agents/{agent_id}")
    if agent_dir.exists():
        print(f"Agent '{agent_id}' already exists")
        return

    agent_dir.mkdir(parents=True, exist_ok=True)

    model = input("LLM Model (default: deepseek-chat): ").strip() or "deepseek-chat"
    api_key = input("API Key: ").strip()
    base_url = (
        input("Base URL (default: https://api.deepseek.com/v1): ").strip()
        or "https://api.deepseek.com/v1"
    )

    metadata = {
        "name": agent_id,
        "llm": {
            "gateway": "openai",
            "provider": "deepseek",
            "model": model,
            "api_key": api_key,
            "base_url": base_url,
            "multimodal": False,
        },
        "context": {"max_tokens": 80000, "unload_threshold_tokens": 80000},
        "extra_workspaces": [],
    }

    metadata_file = agent_dir / "metadata.json"
    metadata_file.write_text(json.dumps(metadata, indent=2))
    print(f"\nAgent '{agent_id}' created successfully")
    print(f"Configuration saved to {metadata_file}")


def cmd_agent_del(agent_name: str):
    """删除 Agent"""
    agent_dir = Path(f"workspace/data/agents/{agent_name}")
    if not agent_dir.exists():
        print(f"Agent '{agent_name}' not found")
        return

    import shutil

    shutil.rmtree(agent_dir)
    print(f"Agent '{agent_name}' deleted")


def cmd_channel_list():
    """列出所有渠道"""
    print("Available channels:")
    print("  - feishu: Feishu integration")
    print("  - imessage: iMessage (Mac only)")
    print("  - telegram: Telegram bot")


def cmd_channel_add(channel_name: str):
    """添加渠道配置"""
    print(f"Adding channel '{channel_name}'...")
    print(
        f"Please configure the channel in workspace/data/channels/{channel_name}/config.json"
    )

    config_dir = Path(f"workspace/data/channels/{channel_name}")
    config_dir.mkdir(parents=True, exist_ok=True)

    config_file = config_dir / "config.json"
    if not config_file.exists():
        config_file.write_text(json.dumps({"enabled": False}, indent=2))


def cmd_channel_enable(channel_name: str):
    """启用渠道"""
    config_file = Path(f"workspace/data/channels/{channel_name}/config.json")
    if not config_file.exists():
        print(f"Channel '{channel_name}' not configured")
        return

    config = json.loads(config_file.read_text())
    config["enabled"] = True
    config_file.write_text(json.dumps(config, indent=2))
    print(f"Channel '{channel_name}' enabled")


def cmd_channel_disable(channel_name: str):
    """禁用渠道"""
    config_file = Path(f"workspace/data/channels/{channel_name}/config.json")
    if not config_file.exists():
        print(f"Channel '{channel_name}' not configured")
        return

    config = json.loads(config_file.read_text())
    config["enabled"] = False
    config_file.write_text(json.dumps(config, indent=2))
    print(f"Channel '{channel_name}' disabled")


def cmd_channel_del(channel_name: str):
    """删除渠道配置"""
    config_dir = Path(f"workspace/data/channels/{channel_name}")
    if not config_dir.exists():
        print(f"Channel '{channel_name}' not configured")
        return

    import shutil

    shutil.rmtree(config_dir)
    print(f"Channel '{channel_name}' deleted")


def cmd_init():
    """初始化配置"""
    print("Initializing FastClaw configuration...")

    base_dir = Path("workspace/data")
    base_dir.mkdir(parents=True, exist_ok=True)

    agents_dir = base_dir / "agents" / "main_agent"
    agents_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "name": "main_agent",
        "llm": {
            "gateway": "openai",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_key": os.getenv("LLM_API_KEY", ""),
            "base_url": os.getenv("LLM_API_URL", "https://api.deepseek.com/v1"),
            "multimodal": False,
        },
        "context": {"max_tokens": 80000, "unload_threshold_tokens": 80000},
        "extra_workspaces": [],
    }

    metadata_file = agents_dir / "metadata.json"
    metadata_file.write_text(json.dumps(metadata, indent=2))

    settings_file = base_dir / "settings.json"
    settings_file.write_text(json.dumps({"default_agent_id": "main_agent"}, indent=2))

    cron_dir = base_dir / "cron"
    cron_dir.mkdir(parents=True, exist_ok=True)

    print("Configuration initialized successfully!")
    print(f"  - Agent config: {metadata_file}")
    print(f"  - Settings: {settings_file}")
    print(f"  - Cron tasks: {cron_dir}")


def cmd_status():
    """查看运行状态"""
    print("FastClaw Status")
    print("=" * 40)

    settings = load_settings()
    print(f"Default Agent: {settings.get('default_agent_id', 'N/A')}")

    skills = load_skills()
    print(f"Skills loaded: {len(skills)}")

    agents_dir = Path("workspace/data/agents")
    if agents_dir.exists():
        agent_count = len([p for p in agents_dir.iterdir() if p.is_dir()])
        print(f"Agents configured: {agent_count}")

    tasks_file = Path("workspace/data/cron/tasks.json")
    if tasks_file.exists():
        tasks = json.loads(tasks_file.read_text())
        enabled = sum(1 for t in tasks if t.get("enabled", False))
        print(f"Cron tasks: {len(tasks)} ({enabled} enabled)")

    sessions_file = Path("workspace/data/sessions/sessions.json")
    if sessions_file.exists():
        sessions = json.loads(sessions_file.read_text())
        print(f"Sessions: {len(sessions)}")


def cmd_help():
    """显示帮助"""
    print("FastClaw CLI")
    print("=" * 50)
    print("\nUsage: python main.py <command> [options]")
    print("\nCommands:")
    print("  start                      Start web server (default)")
    print("  chat                       Start interactive chat")
    print("  api                        Start API server only")
    print("\n  cron list                  List cron tasks")
    print("  cron add                   Add new cron task")
    print("  cron del <name>            Delete cron task")
    print("  cron run <name>            Trigger cron task manually")
    print("\n  session list               List all sessions")
    print("  session history <id>       Show session history")
    print("  session clear <id>         Clear session messages")
    print("  session export <id>        Export session to JSON")
    print("\n  skill list                 List all skills")
    print("  skill info <name>          Show skill details")
    print("  skill test <name>         Test a skill")
    print("\n  agent list                 List all agents")
    print("  agent info <name>          Show agent config")
    print("  agent add                  Add new agent")
    print("  agent del <name>           Delete agent")
    print("\n  channel list               List available channels")
    print("  channel add <name>         Add channel config")
    print("  channel enable <name>      Enable channel")
    print("  channel disable <name>     Disable channel")
    print("  channel del <name>         Delete channel")
    print("\n  init                       Initialize configuration")
    print("  status                     Show system status")
    print("  help                       Show this help")


def run_cli():
    """运行 CLI 命令"""
    if len(sys.argv) < 2:
        cmd_help()
        return

    command = sys.argv[1]

    if command == "cron":
        if len(sys.argv) < 3:
            cmd_cron_list()
        elif sys.argv[2] == "list":
            cmd_cron_list()
        elif sys.argv[2] == "add":
            cmd_cron_add()
        elif sys.argv[2] == "del":
            if len(sys.argv) < 4:
                print("Usage: fastclaw cron del <name>")
            else:
                cmd_cron_del(sys.argv[3])
        elif sys.argv[2] == "run":
            if len(sys.argv) < 4:
                print("Usage: fastclaw cron run <name>")
            else:
                cmd_cron_run(sys.argv[3])
        else:
            print(f"Unknown cron command: {sys.argv[2]}")

    elif command == "session":
        if len(sys.argv) < 3:
            cmd_session_list()
        elif sys.argv[2] == "list":
            cmd_session_list()
        elif sys.argv[2] == "history":
            if len(sys.argv) < 4:
                print("Usage: fastclaw session history <id>")
            else:
                cmd_session_history(sys.argv[3])
        elif sys.argv[2] == "clear":
            if len(sys.argv) < 4:
                print("Usage: fastclaw session clear <id>")
            else:
                cmd_session_clear(sys.argv[3])
        elif sys.argv[2] == "export":
            if len(sys.argv) < 4:
                print("Usage: fastclaw session export <id>")
            else:
                cmd_session_export(sys.argv[3])
        else:
            print(f"Unknown session command: {sys.argv[2]}")

    elif command == "skill":
        if len(sys.argv) < 3:
            cmd_skill_list()
        elif sys.argv[2] == "list":
            cmd_skill_list()
        elif sys.argv[2] == "info":
            if len(sys.argv) < 4:
                print("Usage: fastclaw skill info <name>")
            else:
                cmd_skill_info(sys.argv[3])
        elif sys.argv[2] == "test":
            if len(sys.argv) < 4:
                print("Usage: fastclaw skill test <name>")
            else:
                cmd_skill_test(sys.argv[3])
        else:
            print(f"Unknown skill command: {sys.argv[2]}")

    elif command == "agent":
        if len(sys.argv) < 3:
            cmd_agent_list()
        elif sys.argv[2] == "list":
            cmd_agent_list()
        elif sys.argv[2] == "info":
            if len(sys.argv) < 4:
                print("Usage: fastclaw agent info <name>")
            else:
                cmd_agent_info(sys.argv[3])
        elif sys.argv[2] == "add":
            cmd_agent_add()
        elif sys.argv[2] == "del":
            if len(sys.argv) < 4:
                print("Usage: fastclaw agent del <name>")
            else:
                cmd_agent_del(sys.argv[3])
        else:
            print(f"Unknown agent command: {sys.argv[2]}")

    elif command == "channel":
        if len(sys.argv) < 3:
            cmd_channel_list()
        elif sys.argv[2] == "list":
            cmd_channel_list()
        elif sys.argv[2] == "add":
            if len(sys.argv) < 4:
                print("Usage: fastclaw channel add <name>")
            else:
                cmd_channel_add(sys.argv[3])
        elif sys.argv[2] == "enable":
            if len(sys.argv) < 4:
                print("Usage: fastclaw channel enable <name>")
            else:
                cmd_channel_enable(sys.argv[3])
        elif sys.argv[2] == "disable":
            if len(sys.argv) < 4:
                print("Usage: fastclaw channel disable <name>")
            else:
                cmd_channel_disable(sys.argv[3])
        elif sys.argv[2] == "del":
            if len(sys.argv) < 4:
                print("Usage: fastclaw channel del <name>")
            else:
                cmd_channel_del(sys.argv[3])
        else:
            print(f"Unknown channel command: {sys.argv[2]}")

    elif command == "init":
        cmd_init()

    elif command == "status":
        cmd_status()

    elif command == "help":
        cmd_help()

    else:
        print(f"Unknown command: {command}")
        print("Run 'python main.py help' for usage information")


if __name__ == "__main__":
    run_cli()
