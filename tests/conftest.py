"""Pytest 配置和 fixtures"""

import pytest
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def workspace_dir(tmp_path):
    """创建临时工作空间"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "data").mkdir()
    (workspace / "data" / "sessions").mkdir()
    (workspace / "data" / "cron").mkdir()
    (workspace / "skills").mkdir()
    return workspace
