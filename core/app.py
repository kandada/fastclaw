# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
# app.py
"""FastClaw 核心引擎"""

import sys
import logging
from pathlib import Path

import asyncio
import datetime
import subprocess
import json
import importlib.util
import os
import re
from fastmind import FastMind, Graph, Event, ToolNode
from fastmind.contrib import FastMindAPI
from openai import AsyncOpenAI
import time

if __package__ in (None, ""):
    from core.prompts import format_system_prompt, SYSTEM_PROMPT
else:
    from .prompts import format_system_prompt, SYSTEM_PROMPT

_IS_PACKAGE_MODE = __package__ and __package__.startswith("fastclaw")
if _IS_PACKAGE_MODE:
    from .config import (
        get_workspace_path,
        get_sessions_dir,
        get_agents_dir,
        get_settings_file,
        get_skills_dir,
        get_session_store,
    )
else:
    from core.config import (
        get_workspace_path,
        get_sessions_dir,
        get_agents_dir,
        get_settings_file,
        get_skills_dir,
        get_session_store,
    )

logger = logging.getLogger(__name__)

CONTEXT_UNLOAD_THRESHOLD = 80000

# === 缓存基础设施：减少首 token 延迟 ===

_CACHED_SETTINGS = None
_CACHED_SETTINGS_FILE = None
_CACHED_SETTINGS_MTIME = 0

_AGENT_CONFIG_CACHE = {}
_AGENT_PERSONALITY_CACHE = {}
_LLM_CLIENT_CACHE = {}


def _get_file_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0


def calculate_tokens(text: str) -> int:
    return len(text) // 4


def count_messages_tokens(messages: list) -> int:
    total = 0
    for msg in messages:
        total += calculate_tokens(msg.get("content", ""))
        total += calculate_tokens(msg.get("reasoning_content", ""))
        if msg.get("tool_calls"):
            total += calculate_tokens(json.dumps(msg["tool_calls"]))
    return total


def fix_invalid_tool_calls(messages: list) -> list:
    """修复 messages 历史中不合规的 tool_calls 消息

    如果 assistant 消息有 tool_calls，但后续的 tool 响应未覆盖所有
    tool_call_id，则删除该 assistant 消息的 tool_calls 字段，
    避免 LLM 调用时因 tool 响应不完整而报错。
    """
    fixed = []
    i = 0

    while i < len(messages) and messages[i].get("role") == "tool":
        i += 1

    while i < len(messages):
        msg = messages[i]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            tool_call_ids = {tc["id"] for tc in msg["tool_calls"] if tc.get("id")}
            if not tool_call_ids:
                fixed.append(msg)
                i += 1
                continue
            j = i + 1
            responded_ids = set()
            while j < len(messages) and messages[j].get("role") == "tool":
                tid = messages[j].get("tool_call_id")
                if tid:
                    responded_ids.add(tid)
                j += 1
            if tool_call_ids.issubset(responded_ids):
                fixed.append(msg)
            else:
                msg_copy = dict(msg)
                del msg_copy["tool_calls"]
                fixed.append(msg_copy)
                while i + 1 < len(messages) and messages[i + 1].get("role") == "tool":
                    i += 1
            i += 1
        else:
            fixed.append(msg)
            i += 1
    return fixed


def save_messages_to_jsonl(session_id: str, messages: list) -> None:
    session_dir = get_sessions_dir() / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    messages_file = session_dir / "messages.jsonl"
    with open(messages_file, "w", encoding="utf-8") as f:
        for msg in messages:
            if msg.get("role") in ("user", "assistant", "system", "tool"):
                if "timestamp" not in msg:
                    msg["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    if messages and messages[0].get("role") == "user":
        store = get_session_store()
        sessions = store.load()
        if session_id in sessions and not sessions[session_id].get("name"):
            first_text = messages[0]["content"][:50]
            sessions[session_id]["name"] = first_text
            store.save(sessions)


async def _save_messages_async(session_id: str, messages: list) -> None:
    await asyncio.get_event_loop().run_in_executor(
        None, save_messages_to_jsonl, session_id, messages
    )


def load_messages_from_jsonl(session_id: str) -> list:
    messages_file = get_sessions_dir() / session_id / "messages.jsonl"
    if not messages_file.exists():
        return []
    messages = []
    for line in messages_file.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                msg = json.loads(line)
                messages.append(msg)
            except:
                pass

    return messages


def unload_early_messages(messages: list, threshold: int) -> tuple[list, list]:
    if count_messages_tokens(messages) < threshold:
        return messages, []
    keep_count = len(messages) // 2
    boundary = len(messages) - keep_count
    # 向前调整切割点：不切在 tool 响应中间
    while boundary < len(messages) and messages[boundary].get("role") == "tool":
        boundary += 1
    # 向后调整切割点：若切割点前一条是 assistant(tc)，其 tool 响应可能不全
    while boundary > 0 and messages[boundary - 1].get("role") == "assistant" and \
          messages[boundary - 1].get("tool_calls"):
        boundary -= 1
        while boundary > 0 and messages[boundary - 1].get("role") == "tool":
            boundary -= 1
    kept_messages = messages[boundary:]
    unloaded_messages = messages[:boundary]
    return kept_messages, unloaded_messages


def load_settings() -> dict:
    global _CACHED_SETTINGS, _CACHED_SETTINGS_FILE, _CACHED_SETTINGS_MTIME
    settings_file = get_settings_file()
    mtime = _get_file_mtime(settings_file)
    if (
        _CACHED_SETTINGS is not None
        and settings_file == _CACHED_SETTINGS_FILE
        and mtime == _CACHED_SETTINGS_MTIME
    ):
        return _CACHED_SETTINGS
    defaults = {
        "default_agent_id": "main_agent",
        "run_shell_timeout": 60,
        "run_skills_timeout": 60,
    }
    if settings_file.exists():
        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
            settings = {**defaults, **settings}
        except:
            settings = defaults
    else:
        settings = defaults
    _CACHED_SETTINGS = settings
    _CACHED_SETTINGS_FILE = settings_file
    _CACHED_SETTINGS_MTIME = mtime
    return settings


def load_session_agent_id(session_id: str) -> str:
    sessions_file = get_sessions_dir() / "sessions.json"
    if sessions_file.exists():
        try:
            sessions = json.loads(sessions_file.read_text(encoding="utf-8"))
            if session_id in sessions:
                agent_id = sessions[session_id].get("agent_id", "")
                if agent_id:
                    return agent_id
        except:
            pass
    settings = load_settings()
    return settings.get("default_agent_id", "main_agent")


def load_agent_config(agent_id: str) -> dict:
    agent_dir = get_agents_dir() / agent_id
    metadata_file = agent_dir / "metadata.json"
    mtime = _get_file_mtime(metadata_file)
    cached = _AGENT_CONFIG_CACHE.get(agent_id)
    if cached and cached["mtime"] == mtime:
        return cached["config"]
    if metadata_file.exists():
        try:
            config = json.loads(metadata_file.read_text(encoding="utf-8"))
        except:
            config = _default_agent_config(agent_id)
    else:
        config = _default_agent_config(agent_id)
    _AGENT_CONFIG_CACHE[agent_id] = {"mtime": mtime, "config": config}
    return config


def _default_agent_config(agent_id: str) -> dict:
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
            "unload_threshold_tokens": 156000,
        },
        "extra_workspaces": [],
    }


def load_agent_personality(agent_id: str) -> str:
    agent_dir = get_agents_dir() / agent_id
    personality_files = ["SOUL.md", "USER.md", "AGENT.md"]
    latest_mtime = 0
    for filename in personality_files:
        mtime = _get_file_mtime(agent_dir / filename)
        if mtime > latest_mtime:
            latest_mtime = mtime
    cached = _AGENT_PERSONALITY_CACHE.get(agent_id)
    if cached and cached["mtime"] == latest_mtime:
        return cached["personality"]
    parts = []
    for filename in personality_files:
        filepath = agent_dir / filename
        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(f"\n\n## {filename.replace('.md', '')}\n{content}")
            except:
                pass
    personality = "".join(parts)
    _AGENT_PERSONALITY_CACHE[agent_id] = {"mtime": latest_mtime, "personality": personality}
    return personality


def find_skill_md(skill_dir: Path) -> Path | None:
    """在技能目录中大小写不敏感地定位 SKILL.md（兼容 skill.md / Skill.md）。"""
    skill_dir = Path(skill_dir)
    direct = skill_dir / "SKILL.md"
    if direct.exists():
        return direct
    if skill_dir.is_dir():
        for child in skill_dir.iterdir():
            if child.is_file() and child.name.lower() == "skill.md":
                return child
    return None


def parse_skill_description(content: str) -> str:
    """解析技能简介：优先 YAML frontmatter 的 description，回退到 ## Description 段落（支持多行）。"""
    fm = re.match(r"^\ufeff?\s*---\s*\n(.*?)\n---\s*(?:\n|$)", content, re.DOTALL)
    if fm:
        m = re.search(r"^\s*description\s*:\s*(.+?)\s*$", fm.group(1), re.MULTILINE)
        if m:
            desc = m.group(1).strip().strip('"').strip("'").strip()
            if desc:
                return desc
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("## description"):
            collected = []
            for nxt in lines[i + 1:]:
                s = nxt.strip()
                if s.startswith("## "):
                    break
                if s == "":
                    if collected:
                        break
                    continue
                collected.append(s)
            desc = " ".join(collected).strip()
            if desc:
                return desc
            break
    return ""


def list_skill_resources(skill_dir: Path) -> list:
    """列出技能目录内除 SKILL.md 之外可供按需读取的资源文件（相对路径）。"""
    skill_dir = Path(skill_dir)
    if not skill_dir.is_dir():
        return []
    out = []
    for p in sorted(skill_dir.rglob("*")):
        if not p.is_file():
            continue
        if p.name.lower() == "skill.md":
            continue
        rel = p.relative_to(skill_dir)
        if any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
            continue
        out.append(str(rel))
    return out


def load_skills(skills_dir: str = None) -> dict:
    skills = {}
    if skills_dir is None:
        skills_dir_path = get_skills_dir()
    else:
        skills_dir_path = Path(skills_dir)
    if not skills_dir_path.exists():
        return skills
    seen = set()
    for md_path in skills_dir_path.rglob("*"):
        if not md_path.is_file() or md_path.name.lower() != "skill.md":
            continue
        skill_dir = md_path.parent
        key = str(skill_dir).lower()
        if key in seen:
            continue
        seen.add(key)
        skill_name = skill_dir.name
        if skill_name.startswith("_"):
            continue
        content = md_path.read_text(encoding="utf-8")
        desc = parse_skill_description(content)
        skills[skill_name] = {
            "name": skill_name,
            "description": desc or f"{skill_name} skill",
            "path": str(skill_dir),
        }
    return skills


def find_skill_entry(skill_dir: Path) -> Path | None:
    """定位技能入口脚本：优先 main.py；否则若目录顶层恰好只有一个非下划线开头的 .py 文件，用它作入口；否则 None（视为文档技能）。"""
    skill_dir = Path(skill_dir)
    if not skill_dir.is_dir():
        return None
    main = skill_dir / "main.py"
    if main.exists():
        return main
    candidates = [
        p for p in sorted(skill_dir.glob("*.py"))
        if p.is_file() and not p.name.startswith("_")
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None


def render_doc_skill(skill_name: str, skill_dir: Path, params: dict = None) -> str:
    """文档型技能（无 main.py）：返回 SKILL.md 指引内容 + 可用资源清单 + 参数提示。"""
    skill_dir = Path(skill_dir)
    md = find_skill_md(skill_dir)
    if md is None:
        return f"Error: Skill '{skill_name}' not found at {skill_dir}"
    parts = [md.read_text(encoding="utf-8").rstrip()]
    resources = list_skill_resources(skill_dir)
    if resources:
        parts.append(
            "\n## Available Resources (read on demand with run_shell)\n"
            + "\n".join(f"- {r}" for r in resources)
        )
    if params:
        parts.append(
            f"\n(Note: this is a document-only skill with no executable script; "
            f"the provided params {list(params.keys())} were not consumed. "
            f"Follow the instructions above and perform the steps yourself via run_shell.)"
        )
    return "\n".join(parts)


async def execute_skill(
    skill_name: str, params: dict = None, skill_dir: str = None, timeout: int = 60
) -> str:
    params = dict(params) if params else {}
    if skill_dir is None:
        skill_dir = str(get_skills_dir() / skill_name)
    skill_path = find_skill_entry(Path(skill_dir))
    if skill_path is None:
        return render_doc_skill(skill_name, Path(skill_dir), params)
    settings = load_settings()
    raw = settings.get("run_skills_timeout", 60)
    effective_timeout = timeout if isinstance(timeout, (int, float)) and timeout > 0 else (raw if isinstance(raw, (int, float)) and raw > 0 else 60)

    def _public_async_funcs(mod) -> list:
        return [
            name for name, obj in vars(mod).items()
            if callable(obj) and asyncio.iscoroutinefunction(obj) and not name.startswith("_")
        ]

    async def _await_and_str(fn, **kw) -> str:
        try:
            result = await asyncio.wait_for(
                fn(**kw), timeout=effective_timeout
            )
            return str(result)
        except asyncio.TimeoutError:
            return f"Error: Skill '{skill_name}' timed out ({effective_timeout}s)"

    try:
        spec = importlib.util.spec_from_file_location("skill_module", skill_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, "execute"):
            return await _await_and_str(module.execute, **params)

        if "func" in params:
            func_name = params.pop("func")
            if hasattr(module, func_name) and callable(getattr(module, func_name)):
                fn = getattr(module, func_name)
                return await _await_and_str(fn, **params)
            public_funcs = _public_async_funcs(module)
            return f"Error: Skill '{skill_name}' has no function '{func_name}'. Available: {', '.join(public_funcs)}"

        if hasattr(module, "run"):
            return await _await_and_str(module.run, **params)

        public_funcs = _public_async_funcs(module)
        if len(public_funcs) == 1:
            fn = getattr(module, public_funcs[0])
            return await _await_and_str(fn, **params)

        if public_funcs:
            return f"Error: Skill '{skill_name}' has multiple functions, specify 'func' param. Available: {', '.join(public_funcs)}"

        return f"Error: Skill '{skill_name}' has no executable function"
    except Exception as e:
        return f"Error executing skill '{skill_name}': {str(e)}"


def _try_register_skill(skill_name: str) -> bool:
    skills_dir = get_skills_dir()
    for md_path in skills_dir.rglob("*"):
        if not md_path.is_file() or md_path.name.lower() != "skill.md":
            continue
        if md_path.parent.name == skill_name:
            content = md_path.read_text(encoding="utf-8")
            desc = parse_skill_description(content)
            SKILLS[skill_name] = {
                "name": skill_name,
                "description": desc or f"{skill_name} skill",
                "path": str(md_path.parent),
            }
            return True
    return False


app = FastMind()

SKILLS = load_skills()

SKILLS_LIST = (
    "\n".join([f"- {name}: {info['description']}" for name, info in SKILLS.items()])
    or "- (No built-in skills)"
)

SYSTEM_PROMPT_TEMPLATE = SYSTEM_PROMPT.replace("{skills_list}", SKILLS_LIST)

WORKSPACE_PATH = get_workspace_path()
CONFIRM_PREFIX = "CONFIRM:"


def _get_llm_client(llm_config: dict) -> AsyncOpenAI:
    api_key = llm_config.get("api_key", "")
    base_url = llm_config.get("base_url", "https://api.deepseek.com/v1")
    timeout = llm_config.get("timeout", 120) or 120
    cache_key = (api_key, base_url, timeout)
    client = _LLM_CLIENT_CACHE.get(cache_key)
    if client is None:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        _LLM_CLIENT_CACHE[cache_key] = client
    return client


DENY_PATTERNS = [
    (re.compile(r"rm\s+-rf\s+/\s*$"), "rm -rf / (recursive root deletion, destroys system)"),
    (re.compile(r"rm\s+-rf\s+/\s"), "rm -rf / (recursive root deletion, destroys system)"),
    (re.compile(r"\bmkfs\b"), "mkfs (format disk, destroys data)"),
    (re.compile(r"\bmkfs\."), "mkfs.* (format disk, destroys data)"),
    (re.compile(r"\bnewfs\b"), "newfs (create filesystem, destroys data)"),
    (re.compile(r"\bwipefs\b"), "wipefs (erase filesystem header)"),
    (re.compile(r"\bdd\s+.*of=/dev/"), "dd write to device (may corrupt disk)"),
    (re.compile(r"\bdd\s+.*of=/dev/sd"), "dd write to device (may corrupt disk)"),
    (re.compile(r"\bdd\s+.*of=/dev/nvme"), "dd write to device (may corrupt disk)"),
    (re.compile(r"\bfdisk\b.*-d"), "fdisk -d (delete partition)"),
    (re.compile(r"\bparted\b.*rm"), "parted rm (delete partition)"),
    (re.compile(r"\bsfdisk\b.*-d"), "sfdisk -d (delete partition)"),
    (re.compile(r"\bcryptsetup\b.*lukserase"), "cryptsetup luksErase (erase LUKS header)"),
    (re.compile(r"\bcryptsetup\b.*luksclose"), "cryptsetup luksClose (close encrypted volume)"),
    (re.compile(r"\bveracrypt\b.*-d"), "veracrypt -d (decrypt volume, loses data)"),
    (re.compile(r"\bkill\s+-9\s+1\b"), "kill -9 1 (kill init process)"),
    (re.compile(r"\bpkill\s+-9\s+-1\b"), "pkill -9 -1 (kill all processes)"),
    (re.compile(r"\bkillall\s+-9\b"), "killall -9 (force kill all processes)"),
    (
        re.compile(r"\bchattr\s+-i\b.*(passwd|shadow|group|gshadow)"),
        "chattr -i lock system files",
    ),
    (
        re.compile(r"\bchattr\s+-a\b.*(passwd|shadow|group|gshadow)"),
        "chattr -a modify system files",
    ),
]

ASK_USER_PATTERNS = [
    (re.compile(r"rm\s+-rf\s+\*\s*$"), "rm -rf * (recursive delete, may remove important files)"),
    (re.compile(r"rm\s+-rf\s+\."), "rm -rf . (delete current directory)"),
    (re.compile(r":\(\)\{:\|:&\};:"), "fork bomb (exhausts system resources)"),
    (re.compile(r"\bshutdown\b"), "shutdown (shut down system)"),
    (re.compile(r"\breboot\b"), "reboot (reboot system)"),
    (re.compile(r"\bhalt\b"), "halt (halt system)"),
    (re.compile(r"\bpoweroff\b"), "poweroff (power off system)"),
    (re.compile(r"\binit\s+0\b"), "init 0 (shut down system)"),
    (re.compile(r"\binit\s+6\b"), "init 6 (reboot system)"),
    (re.compile(r">\s*/dev/sd"), "redirect to disk device (may corrupt data)"),
    (re.compile(r">\s*/dev/null\s*>&"), "redirect to null and close output (may lose data)"),
]

SYSTEM_CORE_PATHS = [
    "/etc/",
    "/usr/",
    "/sbin/",
    "/bin/",
    "/sys/",
    "/proc/",
    "/dev/",
    "/Users/xiefujin_mac2025/test/",
]

HARMLESS_DEVICES = [
    "/dev/null",
    "/dev/zero",
    "/dev/full",
    "/dev/urandom",
    "/dev/random",
]

CODE_CORE_PATHS = [
    "core/",
    "gateway/",
    "webui/",
]


def strip_heredocs(text: str) -> str:
    """去掉 heredoc 内容，只保留命令结构供安全检测"""
    return re.sub(
        r"<<\s*'?(\w+)'?\s*\n.*?\n\1\s*",
        " ",
        text,
        flags=re.DOTALL,
    )


def check_command_permission(
    command: str, extra_workspaces: list = None
) -> tuple[str, str]:
    extra_workspaces = extra_workspaces or []
    workspace_str = str(WORKSPACE_PATH.resolve())
    command_lower = strip_heredocs(command).lower()

    for pattern, desc in DENY_PATTERNS:
        if pattern.search(command_lower):
            return (
                "deny",
                f"Dangerous command blocked ({desc}). Use a safer approach if needed.",
            )

    for pattern, desc in ASK_USER_PATTERNS:
        if pattern.search(command_lower):
            return (
                "ask_user",
                f"Sensitive operation detected ({desc}). Ask the user for permission. If confirmed, re-run with: {CONFIRM_PREFIX} <command>",
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
                if any(
                    path_str.endswith(hd) or path_str == hd for hd in HARMLESS_DEVICES
                ):
                    continue
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
            f"This operation is restricted. Ask the user for permission. If confirmed, re-run with: {CONFIRM_PREFIX} <command>",
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


@app.tool(name="run_shell", description="Execute a shell command and return output. Use max_length to control output length, timeout to control execution time.")
async def run_shell(
    command: str,
    max_length: int = 8000,
    timeout: int = 60,
    state: dict = None,
) -> str:
    # (c) 2024-2026 xiefujin <490021684@qq.com> GPLv3
    confirmed = False
    if command.startswith(CONFIRM_PREFIX):
        command = command[len(CONFIRM_PREFIX) :].strip()
        confirmed = True

    extra_workspaces = []
    if state and "_agent_config" in state:
        extra_workspaces = state["_agent_config"].get("extra_workspaces", [])

    permission, reason = check_command_permission(command, extra_workspaces)
    logger.debug("run_shell permission=%s reason=%s", permission, reason)

    if permission == "ask_user" and confirmed:
        permission = "allow"

    if permission == "ask_user":
        if state is not None:
            if "_ask_user_commands" not in state:
                state["_ask_user_commands"] = []
            if command in state["_ask_user_commands"]:
                return (
                    f"AskUser: {reason} "
                    "(You already attempted this command. "
                    "Do NOT repeat it without the CONFIRM: prefix.)"
                )
            state["_ask_user_commands"].append(command)
        return f"AskUser: {reason}"
    elif permission == "deny":
        return f"Permission denied: {reason}"

    settings = load_settings()
    raw = settings.get("run_shell_timeout", 60)
    effective_timeout = timeout if isinstance(timeout, (int, float)) and timeout > 0 else (raw if isinstance(raw, (int, float)) and raw > 0 else 60)

    logger.debug("run_shell executing cmd_len=%d timeout=%d", len(command), effective_timeout)
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=effective_timeout
            )
            output = (stdout or stderr).decode()
            if not output.strip():
                return "(command completed, no output)"
            limit = max_length if max_length is not None else 8000
            if limit != -1 and len(output) > limit:
                output = output[:limit] + f"\n...(truncated, {len(output)} total chars)"
            return output
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return f"Error: Command timed out ({effective_timeout}s)"
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise
    except asyncio.CancelledError:
        raise
    except Exception as e:
        return f"Error: {str(e)}"


# Improve tool schema parameter descriptions
_shell_tool = app._tool_registry.get("run_shell")
if _shell_tool:
    _schema = _shell_tool.to_openai_schema()
    _props = _schema.get("function", {}).get("parameters", {}).get("properties", {})
    if "command" in _props:
        _props["command"]["description"] = "The shell command to execute"
    if "max_length" in _props:
        _props["max_length"]["description"] = "Maximum output characters. Default 8000. Pass -1 for full output (optional)."
    if "timeout" in _props:
        _props["timeout"]["description"] = "Command timeout in seconds. Default 60 (optional)."
    _shell_tool.schema = _schema

_skills_tool = app._tool_registry.get("run_skills")
if _skills_tool:
    _schema = _skills_tool.to_openai_schema()
    _props = _schema.get("function", {}).get("parameters", {}).get("properties", {})
    if "timeout" in _props:
        _props["timeout"]["description"] = "Skill execution timeout in seconds. Default 60 (optional)."
    _skills_tool.schema = _schema


@app.tool(name="run_skills", description="Execute a predefined skill. Use timeout to control execution time.")
async def run_skills(skill_name: str = None, params: dict = None, timeout: int = 60) -> str:
    # (c) 2024-2026 xiefujin <490021684@qq.com> GPLv3
    params = params or {}
    if skill_name in ("__list__", "list", None, ""):
        SKILLS.clear()
        SKILLS.update(load_skills())
        if not SKILLS:
            return "No skills available"
        lines = ["Available skills:"]
        for name, info in SKILLS.items():
            lines.append(f"- {name}: {info['description']}")
        return "\n".join(lines)
    if skill_name in ("__info__", "info"):
        target_skill = params.get("skill_name", "")
        if not target_skill:
            return "Error: skill_name is required for __info__ mode"
        if target_skill not in SKILLS and not _try_register_skill(target_skill):
            return f"Error: Skill '{target_skill}' not found"
        skill_info = SKILLS[target_skill]
        skill_md_path = find_skill_md(Path(skill_info["path"]))
        if skill_md_path is not None:
            return skill_md_path.read_text(encoding="utf-8")
        return f"Skill: {target_skill}\nDescription: {skill_info['description']}"
    if skill_name not in SKILLS and not _try_register_skill(skill_name):
        return f"Error: Skill '{skill_name}' not found"
    skill_info = SKILLS[skill_name]
    skill_path = skill_info["path"]
    return await execute_skill(skill_name, params, skill_dir=skill_path, timeout=timeout)


async def _aiter_with_timeout(aiter, timeout):
    while True:
        try:
            yield await asyncio.wait_for(aiter.__anext__(), timeout=timeout)
        except StopAsyncIteration:
            break


@app.agent(name="fastclaw_agent", tools=["run_shell", "run_skills"])
async def fastclaw_agent(state: dict, event: Event) -> dict:
    """FastClaw 主 Agent：流式输出 + 同步收集 tool_calls

    核心设计：
    - 流式调用 LLM，同时输出文本给用户、收集 tool_calls
    - 文本通过 output_queue 流式发送
    - tool_calls 收集到 state 中，供 route 判断下一步流向
    - 完整回复保存到 messages，供下一轮对话使用
    """
    # (c) 2024-2026 xiefujin <490021684@qq.com> GPLv3
    session_id = state["_session_id"]
    output_queue = state["_output_queue"]
    settings = load_settings()

    if "_agent_config" not in state:
        def _load_session_data(sid, default_id):
            effective_id = load_session_agent_id(sid) or default_id
            config = load_agent_config(effective_id)
            name = config.get("name", effective_id)
            personality = load_agent_personality(name)
            messages = load_messages_from_jsonl(sid)
            return effective_id, config, name, personality, messages

        default_agent_id = settings.get("default_agent_id", "main_agent")
        effective_agent_id, agent_config, agent_name, personality, existing_messages = (
            await asyncio.to_thread(_load_session_data, session_id, default_agent_id)
        )
        state["_agent_config"] = agent_config
        state["_bound_agent_id"] = effective_agent_id
        state["_personality"] = personality
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
        else:
            # Fallback: 向前查找最近的 assistant(tool_calls) 并插入 tool 响应
            insert_at = None
            for idx in range(len(state["messages"]) - 1, -1, -1):
                if state["messages"][idx].get("role") == "assistant" and state["messages"][idx].get("tool_calls"):
                    insert_at = idx + 1
                    break
            if insert_at is not None:
                for result in state["tool_results"]:
                    tool_call_id = result.get("tool_call_id") or tool_calls_map.get(
                        result.get("tool_name", "")
                    )
                    state["messages"].insert(insert_at, {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": f"[{result['tool_name']}]: {result['result']}",
                    })
                    insert_at += 1
            else:
                logger.warning(
                    "tool_results orphaned: no matching assistant(tool_calls) "
                    "found in messages (session=%s)",
                    session_id,
                )
        if "tool_results" in state:
            del state["tool_results"]
        if "tool_calls" in state:
            del state["tool_calls"]

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

    llm_messages = state["messages"]
    if count_messages_tokens(state["messages"]) >= threshold:
        llm_messages, _ = unload_early_messages(state["messages"], threshold)

    llm_messages = fix_invalid_tool_calls(llm_messages)

    llm_config = agent_config.get("llm", {})

    client = _get_llm_client(llm_config)

    extra_workspaces = agent_config.get("extra_workspaces", [])
    skills_list = "\n".join([f"- {name}: {info['description']}" for name, info in SKILLS.items()]) or "- (No built-in skills)"
    system_prompt = format_system_prompt(
        skills_list, session_id, state.get("_personality", ""), extra_workspaces,
        workspace_path=str(get_workspace_path()),
    )

    full_content = ""
    reasoning_content = ""
    tool_calls_buffer = []
    has_tool_calls = False

    stream_chunk_timeout = settings.get("stream_chunk_timeout", 60) or 60

    ctx_size = sum(len(json.dumps(m, ensure_ascii=False)) for m in llm_messages)
    logger.debug("calling LLM session=%s context_bytes=%d", session_id, ctx_size)
    try:
        stream = await client.chat.completions.create(
            model=llm_config.get("model", "deepseek-chat"),
            messages=[
                {"role": "system", "content": system_prompt},
                *llm_messages,
            ],
            tools=app.get_tool_schemas(),
            stream=True,
        )

        async for chunk in _aiter_with_timeout(stream, stream_chunk_timeout):
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

        await _save_messages_async(session_id, state["messages"])

    except asyncio.CancelledError:
        if full_content:
            assistant_msg = {"role": "assistant", "content": full_content}
            if reasoning_content:
                assistant_msg["reasoning_content"] = reasoning_content
            state["messages"].append(assistant_msg)
        try:
            await _save_messages_async(session_id, state["messages"])
        except Exception:
            pass
        output_queue.put_nowait(
            Event(type="stream.end", payload={}, session_id=session_id)
        )
        return state

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


async def start():
    api = FastMindAPI(app)
    await api.start()
    return api
