# app.py
"""FastClaw 核心引擎"""

import sys
from pathlib import Path

# sys.path.insert(0, str(Path(__file__).parent.parent / "vendor"))

import asyncio
import subprocess
import json
import importlib.util
import os
import re
from fastmind import FastMind, Graph, Event, ToolNode
from fastmind.contrib import FastMindAPI
from openai import AsyncOpenAI

from core.prompts import format_system_prompt, SYSTEM_PROMPT

CONTEXT_UNLOAD_THRESHOLD = 80000


def calculate_tokens(text: str) -> int:
    return len(text) // 4


def count_messages_tokens(messages: list) -> int:
    total = 0
    for msg in messages:
        total += calculate_tokens(msg.get("content", ""))
    return total


def fix_invalid_tool_calls(messages: list) -> list:
    """修复 messages 历史中不合规的 tool_calls 消息

    如果 assistant 消息有 tool_calls 但没有紧跟对应的 tool 响应，
    则删除该 assistant 消息的 tool_calls 字段，避免 LLM 调用时出错。
    """
    fixed = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            tool_call_ids = {tc["id"] for tc in msg["tool_calls"] if tc.get("id")}
            if i + 1 < len(messages):
                next_msg = messages[i + 1]
                if (
                    next_msg.get("role") == "tool"
                    and next_msg.get("tool_call_id") in tool_call_ids
                ):
                    fixed.append(msg)
                    i += 1
                    continue
            msg_copy = dict(msg)
            del msg_copy["tool_calls"]
            fixed.append(msg_copy)
        else:
            fixed.append(msg)
        i += 1
    return fixed


def save_messages_to_jsonl(session_id: str, messages: list) -> None:
    session_dir = Path(f"workspace/data/sessions/{session_id}")
    session_dir.mkdir(parents=True, exist_ok=True)
    messages_file = session_dir / "messages.jsonl"
    with open(messages_file, "w", encoding="utf-8") as f:
        for msg in messages:
            if msg.get("role") in ("user", "assistant", "system", "tool"):
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")


def load_messages_from_jsonl(session_id: str) -> list:
    messages_file = Path(f"workspace/data/sessions/{session_id}/messages.jsonl")
    if not messages_file.exists():
        return []
    messages = []
    for line in messages_file.read_text().splitlines():
        if line.strip():
            try:
                messages.append(json.loads(line))
            except:
                pass
    return messages


def unload_early_messages(messages: list, threshold: int) -> tuple[list, list]:
    if count_messages_tokens(messages) < threshold:
        return messages, []
    keep_count = len(messages) // 2
    kept_messages = messages[-keep_count:]
    unloaded_messages = messages[:-keep_count]
    return kept_messages, unloaded_messages


def load_settings() -> dict:
    settings_file = Path("workspace/data/settings.json")
    if settings_file.exists():
        try:
            return json.loads(settings_file.read_text())
        except:
            pass
    return {"default_agent_id": "main_agent"}


def load_session_agent_id(session_id: str) -> str:
    sessions_file = Path("workspace/data/sessions/sessions.json")
    if sessions_file.exists():
        try:
            sessions = json.loads(sessions_file.read_text())
            if session_id in sessions:
                agent_id = sessions[session_id].get("agent_id", "")
                if agent_id:
                    return agent_id
        except:
            pass
    settings = load_settings()
    return settings.get("default_agent_id", "main_agent")


def load_agent_config(agent_id: str) -> dict:
    agent_dir = Path(f"workspace/data/agents/{agent_id}")
    metadata_file = agent_dir / "metadata.json"
    if metadata_file.exists():
        try:
            return json.loads(metadata_file.read_text())
        except:
            pass
    return {
        "name": agent_id,
        "llm": {
            "gateway": "openai",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_key": os.getenv("LLM_API_KEY", ""),
            "base_url": os.getenv("LLM_API_URL", "https://api.deepseek.com/v1"),
            "multimodal": False,
        },
        "context": {
            "max_tokens": 80000,
            "unload_threshold_tokens": 80000,
        },
        "extra_workspaces": [],
    }


def load_agent_personality(agent_id: str) -> str:
    agent_dir = Path(f"workspace/data/agents/{agent_id}")
    parts = []
    for filename in ["SOUL.md", "USER.md", "AGENT.md"]:
        filepath = agent_dir / filename
        if filepath.exists():
            try:
                content = filepath.read_text().strip()
                if content:
                    parts.append(f"\n\n## {filename.replace('.md', '')}\n{content}")
            except:
                pass
    return "".join(parts)


def load_skills(skills_dir: str = "workspace/skills") -> dict:
    skills = {}
    skills_dir_path = Path(skills_dir)
    if not skills_dir_path.exists():
        return skills
    for skill_path in skills_dir_path.rglob("SKILL.md"):
        skill_dir = skill_path.parent
        skill_name = skill_dir.name
        desc = ""
        if skill_path.exists():
            content = skill_path.read_text()
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line.strip().startswith("## Description") and i + 1 < len(lines):
                    desc = lines[i + 1].strip()
                    break
        skills[skill_name] = {
            "name": skill_name,
            "description": desc or f"{skill_name} skill",
            "path": str(skill_dir),
        }
    return skills


async def execute_skill(
    skill_name: str, params: dict = None, skill_dir: str = None
) -> str:
    params = params or {}
    if skill_dir is None:
        skill_dir = f"workspace/skills/{skill_name}"
    skill_path = Path(skill_dir) / "main.py"
    if not skill_path.exists():
        return f"Error: Skill '{skill_name}' not found at {skill_dir}"
    try:
        spec = importlib.util.spec_from_file_location("skill_module", skill_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if hasattr(module, "execute"):
            result = await module.execute(**params)
            return str(result)
        else:
            return f"Error: Skill '{skill_name}' has no execute() function"
    except Exception as e:
        return f"Error executing skill '{skill_name}': {str(e)}"


app = FastMind()

SKILLS = load_skills()

SKILLS_LIST = (
    "\n".join([f"- {name}: {info['description']}" for name, info in SKILLS.items()])
    or "- (暂无内置 Skills)"
)

SYSTEM_PROMPT_TEMPLATE = SYSTEM_PROMPT.replace("{skills_list}", SKILLS_LIST)

WORKSPACE_PATH = Path("workspace").resolve()
CONFIRM_PREFIX = "CONFIRM:"

DENY_PATTERNS = [
    # 递归删除根目录
    (re.compile(r"rm\s+-rf\s+/\s*$"), "rm -rf / （根目录递归删除，会销毁系统）"),
    (re.compile(r"rm\s+-rf\s+/\s"), "rm -rf / （根目录递归删除，会销毁系统）"),
    # 磁盘分区格式化
    (re.compile(r"\bmkfs\b"), "mkfs （格式化磁盘，会销毁数据）"),
    (re.compile(r"\bmkfs\."), "mkfs.* （格式化磁盘，会销毁数据）"),
    (re.compile(r"\bnewfs\b"), "newfs （创建文件系统，会销毁数据）"),
    (re.compile(r"\bwipefs\b"), "wipefs （擦除文件系统头）"),
    # 直接写入设备
    (re.compile(r"\bdd\s+.*of=/dev/"), "dd 写入设备 （可能破坏磁盘）"),
    (re.compile(r"\bdd\s+.*of=/dev/sd"), "dd 写入设备 （可能破坏磁盘）"),
    (re.compile(r"\bdd\s+.*of=/dev/nvme"), "dd 写入设备 （可能破坏磁盘）"),
    # 分区操作
    (re.compile(r"\bfdisk\b.*-d"), "fdisk -d （删除分区）"),
    (re.compile(r"\bparted\b.*rm"), "parted rm （删除分区）"),
    (re.compile(r"\bsfdisk\b.*-d"), "sfdisk -d （删除分区）"),
    # 加密卷操作（可能永久丢失数据）
    (re.compile(r"\bcryptsetup\b.*lukserase"), "cryptsetup luksErase （擦除加密头）"),
    (re.compile(r"\bcryptsetup\b.*luksclose"), "cryptsetup luksClose （关闭加密卷）"),
    (re.compile(r"\bveracrypt\b.*-d"), "veracrypt -d （解密卷，会丢失数据）"),
    # 强制终止关键进程
    (re.compile(r"\bkill\s+-9\s+1\b"), "kill -9 1 （终止init进程）"),
    (re.compile(r"\bpkill\s+-9\s+-1\b"), "pkill -9 -1 （终止所有进程）"),
    (re.compile(r"\bkillall\s+-9\b"), "killall -9 （强制终止所有进程）"),
    # 修改系统关键属性
    (
        re.compile(r"\bchattr\s+-i\b.*(passwd|shadow|group|gshadow)"),
        "chattr -i 锁定系统文件",
    ),
    (
        re.compile(r"\bchattr\s+-a\b.*(passwd|shadow|group|gshadow)"),
        "chattr -a 修改系统文件",
    ),
]

ASK_USER_PATTERNS = [
    # 递归删除（当前目录或可能误删）
    (re.compile(r"rm\s+-rf\s+\*\s*$"), "rm -rf * （递归删除，可能误删重要文件）"),
    (re.compile(r"rm\s+-rf\s+\."), "rm -rf . （删除当前目录）"),
    # Fork炸弹
    (re.compile(r":\(\)\{:\|:&\};:"), "fork 炸弹 （会让系统资源耗尽）"),
    # 系统关闭/重启
    (re.compile(r"\bshutdown\b"), "shutdown （关闭系统）"),
    (re.compile(r"\breboot\b"), "reboot （重启系统）"),
    (re.compile(r"\bhalt\b"), "halt （关闭系统）"),
    (re.compile(r"\bpoweroff\b"), "poweroff （关闭系统）"),
    (re.compile(r"\binit\s+0\b"), "init 0 （关闭系统）"),
    (re.compile(r"\binit\s+6\b"), "init 6 （重启系统）"),
    # 危险的重定向
    (re.compile(r">\s*/dev/sd"), "重定向到磁盘设备 （可能破坏数据）"),
    (re.compile(r">\s*/dev/null\s*>&"), "重定向到 null 并关闭输出 （可能丢失数据）"),
]

SYSTEM_CORE_PATHS = [
    "/etc/",
    "/usr/",
    "/sbin/",
    "/bin/",
    "/sys/",
    "/proc/",
    "/dev/",
    "/Users/xiefujin_mac2025/test/",  # 测试目录
]

CODE_CORE_PATHS = [
    "core/",
    "gateway/",
    "webui/",
]


def check_command_permission(
    command: str, extra_workspaces: list = None
) -> tuple[str, str]:
    extra_workspaces = extra_workspaces or []
    workspace_str = str(WORKSPACE_PATH.resolve())
    command_lower = command.lower()

    for pattern, desc in DENY_PATTERNS:
        if pattern.search(command_lower):
            return (
                "deny",
                f"禁止执行危险命令（{desc}），此操作被系统拦截，如需执行请使用其他安全方式",
            )

    for pattern, desc in ASK_USER_PATTERNS:
        if pattern.search(command_lower):
            return (
                "ask_user",
                f"检测到敏感操作（{desc}），当前你的这个操作是有限制的，请询问用户是否同意，同意后可继续操作。确认后可输入：{CONFIRM_PREFIX} <原命令>",
            )

    command_paths = extract_paths_from_command(command)

    is_workspace_path = False
    is_extra_workspace_path = False
    is_system_core_path = False
    is_code_core_path = False

    for path in command_paths:
        path_resolved = Path(path).resolve()
        path_str = str(path_resolved)

        if path_str.startswith(workspace_str) or "workspace" in path_str:
            is_workspace_path = True
            continue

        for ew in extra_workspaces:
            ew_resolved = str(Path(ew).resolve())
            if path_str.startswith(ew_resolved):
                is_extra_workspace_path = True
                break

        for sys_path in SYSTEM_CORE_PATHS:
            if sys_path in path_str or sys_path in path:
                is_system_core_path = True
                break

        for code_path in CODE_CORE_PATHS:
            if path.startswith(code_path) or code_path in path:
                is_code_core_path = True
                break

    if is_workspace_path or is_extra_workspace_path:
        return "allow", ""
    elif is_system_core_path or is_code_core_path:
        return (
            "ask_user",
            f"当前你的这个操作是有限制的，请询问用户是否同意，同意后可继续操作。确认后可输入：{CONFIRM_PREFIX} <原命令>",
        )
    else:
        return "allow", ""


def extract_paths_from_command(command: str) -> list:
    paths = []
    tokens = command.replace("\\", " ").split()
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if token.startswith("-"):
            continue
        if re.match(r"^[\w\.\-\/\~]", token):
            if "/" in token or "~" in token or token.startswith("."):
                clean_token = token.rstrip(",;:").rstrip("'").rstrip('"')
                if clean_token and not any(
                    clean_token.startswith(x) for x in ["&&", "||", "|", ";", ">", "<"]
                ):
                    paths.append(clean_token)
    return paths


@app.tool(name="run_shell", description="执行Shell命令并返回输出")
async def run_shell(command: str, state: dict = None) -> str:
    confirmed = False
    if command.startswith(CONFIRM_PREFIX):
        command = command[len(CONFIRM_PREFIX) :].strip()
        confirmed = True

    extra_workspaces = []
    if state and "_agent_config" in state:
        extra_workspaces = state["_agent_config"].get("extra_workspaces", [])

    permission, reason = check_command_permission(command, extra_workspaces)

    if permission == "ask_user" and confirmed:
        permission = "allow"

    if permission == "ask_user":
        return f"AskUser: {reason}"
    elif permission == "deny":
        return f"Permission denied: {reason}"

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
            output = (stdout or stderr).decode()
            return output[:5000]
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return "Error: Command timed out (30s)"
    except Exception as e:
        return f"Error: {str(e)}"


@app.tool(name="run_skills", description="执行预定义的技能")
async def run_skills(skill_name: str = None, params: dict = None) -> str:
    params = params or {}
    if skill_name in ("__list__", "list", None, ""):
        if not SKILLS:
            return "暂无可用技能"
        lines = ["可用技能列表:"]
        for name, info in SKILLS.items():
            lines.append(f"- {name}: {info['description']}")
        return "\n".join(lines)
    if skill_name in ("__info__", "info"):
        target_skill = params.get("skill_name", "")
        if not target_skill:
            return "Error: skill_name is required for __info__ mode"
        if target_skill not in SKILLS:
            return f"Error: Skill '{target_skill}' not found"
        skill_info = SKILLS[target_skill]
        skill_md_path = Path(skill_info["path"]) / "SKILL.md"
        if skill_md_path.exists():
            return skill_md_path.read_text()
        return f"Skill: {target_skill}\nDescription: {skill_info['description']}"
    if skill_name not in SKILLS:
        return f"Error: Skill '{skill_name}' not found"
    skill_info = SKILLS[skill_name]
    skill_path = skill_info["path"]
    return await execute_skill(skill_name, params, skill_dir=skill_path)


@app.agent(name="fastclaw_agent", tools=["run_shell", "run_skills"])
async def fastclaw_agent(state: dict, event: Event) -> dict:
    """FastClaw 主 Agent：流式输出 + 同步收集 tool_calls

    核心设计：
    - 流式调用 LLM，同时输出文本给用户、收集 tool_calls
    - 文本通过 output_queue 流式发送
    - tool_calls 收集到 state 中，供 route 判断下一步流向
    - 完整回复保存到 messages，供下一轮对话使用
    """
    session_id = state["_session_id"]
    output_queue = state["_output_queue"]

    if "_agent_config" not in state:
        settings = load_settings()
        default_agent_id = settings.get("default_agent_id", "main_agent")
        effective_agent_id = load_session_agent_id(session_id) or default_agent_id
        agent_config = load_agent_config(effective_agent_id)
        state["_agent_config"] = agent_config
        state["_bound_agent_id"] = effective_agent_id
        agent_name = agent_config.get("name", effective_agent_id)
        personality = load_agent_personality(agent_name)
        state["_personality"] = personality
        existing_messages = load_messages_from_jsonl(session_id)
        state["messages"] = existing_messages if existing_messages else []
    else:
        current_bound_agent = state.get("_bound_agent_id", "")
        session_current_agent = load_session_agent_id(session_id)
        if session_current_agent and session_current_agent != current_bound_agent:
            settings = load_settings()
            default_agent_id = settings.get("default_agent_id", "main_agent")
            effective_agent_id = session_current_agent or default_agent_id
            agent_config = load_agent_config(effective_agent_id)
            state["_agent_config"] = agent_config
            state["_bound_agent_id"] = effective_agent_id
            agent_name = agent_config.get("name", effective_agent_id)
            personality = load_agent_personality(agent_name)
            state["_personality"] = personality

    user_text = event.payload.get("text", "")

    if state.get("tool_results"):
        tool_calls_map = {}
        if state.get("tool_calls"):
            for tc in state["tool_calls"]:
                func_name = tc.get("function", {}).get("name", "")
                if func_name and tc.get("id"):
                    tool_calls_map[func_name] = tc.get("id")

        last_msg = state["messages"][-1] if state["messages"] else None
        has_valid_tool_context = (
            last_msg
            and last_msg.get("role") == "assistant"
            and last_msg.get("tool_calls")
        )

        if has_valid_tool_context:
            for result in state["tool_results"]:
                tool_call_id = result.get("tool_call_id") or tool_calls_map.get(
                    result.get("tool_name", "")
                )
                state["messages"].append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": f"[{result['tool_name']}]: {result['result']}",
                    }
                )
        if "tool_results" in state:
            del state["tool_results"]
        if "tool_calls" in state:
            del state["tool_calls"]

        save_messages_to_jsonl(session_id, state["messages"])

    user_messages = [
        m
        for m in state["messages"]
        if m.get("role") == "user" and m.get("content") == user_text
    ]
    if not user_messages:
        state["messages"].append({"role": "user", "content": user_text})

    agent_config = state.get("_agent_config", {})
    context_config = agent_config.get("context", {})
    threshold = context_config.get("unload_threshold_tokens", CONTEXT_UNLOAD_THRESHOLD)

    if count_messages_tokens(state["messages"]) >= threshold:
        state["messages"], _ = unload_early_messages(state["messages"], threshold)
        state["_context_unloaded"] = True

    state["messages"] = fix_invalid_tool_calls(state["messages"])

    llm_config = agent_config.get("llm", {})

    client = AsyncOpenAI(
        api_key=llm_config.get("api_key", ""),
        base_url=llm_config.get("base_url", "https://api.deepseek.com/v1"),
    )

    extra_workspaces = agent_config.get("extra_workspaces", [])
    system_prompt = format_system_prompt(
        SKILLS_LIST, session_id, state.get("_personality", ""), extra_workspaces
    )

    full_content = ""
    reasoning_content = ""
    tool_calls_buffer = []
    has_tool_calls = False

    try:
        stream = await client.chat.completions.create(
            model=llm_config.get("model", "deepseek-chat"),
            messages=[
                {"role": "system", "content": system_prompt},
                *state["messages"],
            ],
            tools=app.get_tool_schemas(),
            stream=True,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta

            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                reasoning_content += delta.reasoning_content
                output_queue.put_nowait(
                    Event(
                        type="stream.thinking",
                        payload={"delta": delta.reasoning_content},
                        session_id=session_id,
                    )
                )

            if delta.content:
                if not has_tool_calls:
                    full_content += delta.content
                    output_queue.put_nowait(
                        Event(
                            type="stream.chunk",
                            payload={"delta": delta.content},
                            session_id=session_id,
                        )
                    )

            if delta.tool_calls:
                has_tool_calls = True
                for tc in delta.tool_calls:
                    index = tc.index
                    while len(tool_calls_buffer) <= index:
                        tool_calls_buffer.append(
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        )
                    tc_id = tc.id or ""
                    tc_name = tc.function.name if tc.function else ""
                    tc_args = tc.function.arguments if tc.function else ""
                    for existing_tc in tool_calls_buffer:
                        if (
                            existing_tc.get("id") == tc_id
                            and existing_tc.get("function", {}).get("name") == tc_name
                            and existing_tc.get("function", {}).get("arguments")
                            == tc_args
                        ):
                            break
                    else:
                        if tc.id:
                            tool_calls_buffer[index]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_buffer[index]["function"]["name"] = (
                                    tc.function.name
                                )
                            if tc.function.arguments:
                                tool_calls_buffer[index]["function"]["arguments"] += (
                                    tc.function.arguments
                                )

        if has_tool_calls:
            if tool_calls_buffer:
                seen = set()
                unique_tool_calls = []
                for tc in tool_calls_buffer:
                    tc_signature = (
                        tc.get("id", ""),
                        tc.get("function", {}).get("name", ""),
                        tc.get("function", {}).get("arguments", ""),
                    )
                    if tc_signature not in seen:
                        seen.add(tc_signature)
                        unique_tool_calls.append(tc)
                tool_calls_buffer = unique_tool_calls
                state["tool_calls"] = tool_calls_buffer
            output_queue.put_nowait(
                Event(
                    type="stream.fragment",
                    payload={
                        "content": full_content,
                        "has_tool_calls": True,
                        "tool_calls": tool_calls_buffer,
                    },
                    session_id=session_id,
                )
            )
        else:
            output_queue.put_nowait(
                Event(type="stream.end", payload={}, session_id=session_id)
            )

        if full_content or has_tool_calls:
            content_to_save = full_content or ""

            assistant_msg = {"role": "assistant", "content": content_to_save}
            if reasoning_content:
                assistant_msg["reasoning_content"] = reasoning_content
            if tool_calls_buffer:
                assistant_msg["tool_calls"] = tool_calls_buffer
            state["messages"].append(assistant_msg)

        save_messages_to_jsonl(session_id, state["messages"])

    except Exception as e:
        if "tool_calls" in state:
            del state["tool_calls"]
        output_queue.put_nowait(
            Event(type="stream.error", payload={"error": str(e)}, session_id=session_id)
        )

    return state


tool_node = ToolNode(app.get_tools())


def route(state: dict, event: Event) -> str:
    # print(f"[ROUTE] tool_calls in state: {bool(state.get('tool_calls'))}", file=sys.stderr)
    if state.get("tool_calls"):
        return "tools"
    elif state.get("_end"):
        return "__end__"
    else:
        return None


graph = Graph()
graph.add_node("agent", fastclaw_agent)
graph.add_node("tools", tool_node)

graph.add_conditional_edges("agent", route, {"tools": "tools", None: "__end__"})

graph.add_edge("tools", "agent")

graph.set_entry_point("agent")
app.register_graph("main", graph)


@app.perception(interval=60.0, name="cron_checker")
async def cron_checker(app: FastMind):
    import datetime

    BASE_DIR = Path(__file__).parent.parent.resolve()
    CRON_TASKS_FILE = BASE_DIR / "workspace" / "data" / "cron" / "tasks.json"
    SESSIONS_DIR = BASE_DIR / "workspace" / "data" / "sessions"

    def get_latest_session_id() -> str:
        sessions_dir = SESSIONS_DIR
        if not sessions_dir.exists():
            return "default"
        sessions = []
        for session_path in sessions_dir.iterdir():
            if session_path.is_dir():
                metadata_file = session_path / "metadata.json"
                if metadata_file.exists():
                    try:
                        metadata = json.loads(metadata_file.read_text())
                        last_active = metadata.get("last_active_time", 0)
                    except:
                        last_active = 0
                else:
                    last_active = 0
                sessions.append((last_active, session_path.name))
        if not sessions:
            return "default"
        sessions.sort(reverse=True)
        return sessions[0][1]

    def should_run(now: datetime.datetime, schedule: str) -> bool:
        parts = schedule.split()
        if len(parts) != 5:
            return False
        minute = parts[0]
        if minute == "*":
            return True
        if now.minute == int(minute):
            return True
        return False

    tasks = []
    if CRON_TASKS_FILE.exists():
        try:
            tasks = json.loads(CRON_TASKS_FILE.read_text())
        except:
            tasks = []

    now = datetime.datetime.now()

    for task in tasks:
        if not task.get("enabled", False):
            continue
        if should_run(now, task["schedule"]):
            target_session = task.get("session_id") or get_latest_session_id()
            agent_id = task.get("agent_id", "main_agent")
            yield Event(
                type="cron.triggered",
                payload={
                    "task_id": task["id"],
                    "task_name": task["name"],
                    "description": task.get("description", ""),
                    "agent_id": agent_id,
                },
                session_id=target_session,
            )


async def start():
    api = FastMindAPI(app)
    await api.start()
    return api
