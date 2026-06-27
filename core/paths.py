# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""
FastClaw 统一路径访问模块

提供全局路径访问点，避免硬编码 workspace 路径
"""

import os
from pathlib import Path

from fastclaw.core.config import get_workspace_path

WORKSPACE = get_workspace_path()
DATA_DIR = WORKSPACE / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
AGENTS_DIR = DATA_DIR / "agents"
CHANNELS_DIR = DATA_DIR / "channels"
CRON_DIR = DATA_DIR / "cron"
SKILLS_DIR = WORKSPACE / "skills"

SESSION_DB_FILE = SESSIONS_DIR / "sessions.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
