"""Pytest 配置和 fixtures"""

import pytest
import pytest_asyncio
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.app import app, start


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def shared_api():
    """共享的 FastMindAPI 实例，整个测试会话复用"""
    api = await start()
    yield api
    await api.stop()


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


@pytest.fixture
def unique_session_id():
    """生成唯一 session ID 用于测试"""
    return f"test_session_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def main_agent_id():
    """返回 main_agent ID"""
    return "main_agent"


def cleanup_test_session(session_id: str):
    """清理测试 session"""
    from gateway.router import load_sessions, save_sessions
    import shutil

    sessions = load_sessions()
    if session_id in sessions:
        del sessions[session_id]
        save_sessions(sessions)

    session_dir = Path(f"workspace/data/sessions/{session_id}")
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)


def cleanup_test_sessions(session_ids: list):
    """清理多个测试 session"""
    for session_id in session_ids:
        cleanup_test_session(session_id)


def pytest_runtest_setup(item):
    """测试开始前的设置"""
    pass


def pytest_runtest_teardown(item, nextitem):
    """测试结束后的清理"""
    pass


@pytest.fixture
def backup_sessions_json():
    """备份和恢复 sessions.json"""
    import shutil
    from gateway.router import SESSION_DB_FILE

    backup_file = None
    if SESSION_DB_FILE.exists():
        backup_file = SESSION_DB_FILE.with_suffix(".json.bak")
        shutil.copy(SESSION_DB_FILE, backup_file)

    yield

    if backup_file and backup_file.exists():
        shutil.copy(backup_file, SESSION_DB_FILE)
        backup_file.unlink()
    elif SESSION_DB_FILE.exists():
        SESSION_DB_FILE.unlink()
