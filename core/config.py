"""
FastClaw 配置模块

统一管理 workspace 路径、sessions 持久化等配置
"""

import json
import os
import shutil
import threading
import time
from pathlib import Path
from functools import lru_cache


@lru_cache
def get_workspace_path() -> Path:
    """
    获取 workspace 路径，优先级：
    1. FASTCLAW_WORKSPACE 环境变量（最高优先级）
    2. fastclaw/ 包自身目录下的 workspace/（开源模式）
    3. 项目根目录的 workspace/（开发模式）
    4. ~/.fastclaw/workspace（用户目录模式）
    """
    env_path = os.environ.get("FASTCLAW_WORKSPACE")
    if env_path:
        return Path(env_path).resolve()

    _pkg_dir = Path(__file__).parent.parent.resolve()
    _project_root = _pkg_dir.parent

    _pkg_workspace = _pkg_dir / "workspace"
    if _pkg_workspace.exists() and _pkg_workspace.is_dir():
        return _pkg_workspace.resolve()

    _dev_workspace = _project_root / "workspace"
    if _dev_workspace.exists() and _dev_workspace.is_dir():
        return _dev_workspace.resolve()

    return (Path.home() / ".fastclaw" / "workspace").resolve()


def ensure_workspace():
    """
    确保 workspace 基础目录结构存在，不存在则创建。

    创建的目录：
      data/ agents/ sessions/ channels/ cron/
      skills/ bundled/ user/

    注意：本函数只创建空目录结构，不复制任何文件。
    文件复制由 bootstrap.copy_seed_files 负责。
    """
    ws = get_workspace_path()

    if not ws.exists():
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "data").mkdir(parents=True, exist_ok=True)
        (ws / "data" / "agents").mkdir(parents=True, exist_ok=True)
        (ws / "data" / "sessions").mkdir(parents=True, exist_ok=True)
        (ws / "data" / "channels").mkdir(parents=True, exist_ok=True)
        (ws / "data" / "cron").mkdir(parents=True, exist_ok=True)
        (ws / "skills").mkdir(parents=True, exist_ok=True)
        (ws / "skills" / "bundled").mkdir(parents=True, exist_ok=True)
        (ws / "skills" / "user").mkdir(parents=True, exist_ok=True)

    return ws


def get_data_dir() -> Path:
    return get_workspace_path() / "data"


def get_sessions_dir() -> Path:
    return get_workspace_path() / "data" / "sessions"


def get_agents_dir() -> Path:
    return get_workspace_path() / "data" / "agents"


def get_channels_dir() -> Path:
    return get_workspace_path() / "data" / "channels"


def get_cron_dir() -> Path:
    return get_workspace_path() / "data" / "cron"


def get_skills_dir() -> Path:
    return get_workspace_path() / "skills"


def get_settings_file() -> Path:
    return get_workspace_path() / "data" / "settings.json"


_DEFAULT_SETTINGS = {
    "default_agent_id": "main_agent",
    "run_shell_timeout": 60,
    "run_skills_timeout": 60,
}


def ensure_settings():
    """
    确保 settings.json 存在，不存在则用硬编码默认值创建。

    这是兜底逻辑：正常情况下 settings.json 由 bootstrap.copy_seed_files
    从包内置种子复制。如果种子也不存在（极端情况），用此处的硬编码默认值。
    """
    settings_file = get_settings_file()
    if settings_file.exists():
        return
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(
        json.dumps(_DEFAULT_SETTINGS, indent=2, ensure_ascii=False)
    )


class SessionStore:
    """Thread-safe session storage backed by sessions.json.

    Uses a threading.Lock to protect all read/write operations,
    preventing lost-update races from concurrent run_in_executor calls.
    """

    def __init__(self):
        self._lock = threading.Lock()

    @property
    def db_file(self):
        return get_sessions_dir() / "sessions.json"

    def ensure_db(self):
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.db_file.exists():
            self.db_file.write_text("{}")

    def load(self) -> dict:
        with self._lock:
            self.ensure_db()
            try:
                return json.loads(self.db_file.read_text())
            except Exception:
                time.sleep(0.05)
                try:
                    return json.loads(self.db_file.read_text())
                except Exception:
                    return {}

    def save(self, sessions: dict):
        with self._lock:
            self.ensure_db()
            self.db_file.write_text(
                json.dumps(sessions, indent=2, ensure_ascii=False)
            )


_session_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store
