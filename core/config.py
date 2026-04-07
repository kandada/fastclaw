"""
FastClaw 配置模块

统一管理 workspace 路径等配置
"""

import os
import shutil
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
    确保 workspace 存在，不存在则创建基础目录结构
    返回 workspace 路径
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
