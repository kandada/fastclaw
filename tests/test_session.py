"""Session 管理测试"""

import pytest
import asyncio
from pathlib import Path
import json
import uuid

from gateway.router import (
    load_sessions,
    save_sessions,
    ensure_sessions_db,
    SESSION_DB_FILE,
)


class TestSessionStorage:
    """Session 存储测试"""

    def test_ensure_sessions_db_creates_file(self, tmp_path):
        """测试 ensure_sessions_db 创建数据库文件"""
        SESSION_DB_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Clean up any existing file
        if SESSION_DB_FILE.exists():
            SESSION_DB_FILE.unlink()

        ensure_sessions_db()

        assert SESSION_DB_FILE.exists()
        assert SESSION_DB_FILE.read_text() == "{}"

    def test_save_and_load_sessions(self, tmp_path):
        """测试保存和加载 sessions"""
        sessions = {
            "test_session": {
                "session_id": "test_session",
                "agent_id": "main_agent",
                "created_at": "1234567890",
                "last_active_time": 0,
            }
        }

        save_sessions(sessions)
        loaded = load_sessions()

        assert "test_session" in loaded
        assert loaded["test_session"]["agent_id"] == "main_agent"

    def test_load_sessions_empty(self, tmp_path):
        """测试加载空的 sessions"""
        SESSION_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_DB_FILE.write_text("{}")

        sessions = load_sessions()
        assert sessions == {}

    def test_load_sessions_invalid_json(self, tmp_path):
        """测试加载无效 JSON"""
        SESSION_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_DB_FILE.write_text("invalid json")

        sessions = load_sessions()
        assert sessions == {}


class TestSessionCreate:
    """Session 创建测试"""

    def test_session_create_generates_id(self):
        """测试创建 session 生成 ID"""
        sessions = load_sessions()

        session_id = str(uuid.uuid4())[:8]

        sessions[session_id] = {
            "session_id": session_id,
            "agent_id": "main_agent",
            "created_at": str(uuid.uuid4()),
            "last_active_time": 0,
        }

        save_sessions(sessions)

        loaded = load_sessions()
        assert session_id in loaded

    def test_session_create_with_agent(self):
        """测试指定 agent 创建 session"""
        sessions = load_sessions()

        session_id = "custom_agent_session"

        sessions[session_id] = {
            "session_id": session_id,
            "agent_id": "custom_agent",
            "created_at": str(uuid.uuid4()),
            "last_active_time": 0,
        }

        save_sessions(sessions)

        loaded = load_sessions()
        assert loaded[session_id]["agent_id"] == "custom_agent"


class TestSessionUpdate:
    """Session 更新测试"""

    def test_session_update_agent(self):
        """测试更新 session 的 agent"""
        sessions = load_sessions()

        session_id = "update_test"
        sessions[session_id] = {
            "session_id": session_id,
            "agent_id": "main_agent",
            "created_at": str(uuid.uuid4()),
            "last_active_time": 0,
        }

        save_sessions(sessions)

        # Update
        sessions[session_id]["agent_id"] = "new_agent"
        save_sessions(sessions)

        loaded = load_sessions()
        assert loaded[session_id]["agent_id"] == "new_agent"


class TestSessionDelete:
    """Session 删除测试"""

    def test_session_delete(self):
        """测试删除 session"""
        sessions = load_sessions()

        session_id = "delete_test"
        sessions[session_id] = {
            "session_id": session_id,
            "agent_id": "main_agent",
            "created_at": str(uuid.uuid4()),
            "last_active_time": 0,
        }

        save_sessions(sessions)
        assert session_id in load_sessions()

        del sessions[session_id]
        save_sessions(sessions)

        loaded = load_sessions()
        assert session_id not in loaded


class TestSessionList:
    """Session 列表测试"""

    def test_session_list_multiple(self):
        """测试列出多个 sessions"""
        sessions = load_sessions()

        for i in range(3):
            session_id = f"list_test_{i}"
            sessions[session_id] = {
                "session_id": session_id,
                "agent_id": "main_agent",
                "created_at": str(uuid.uuid4()),
                "last_active_time": 0,
            }

        save_sessions(sessions)

        loaded = load_sessions()
        for i in range(3):
            assert f"list_test_{i}" in loaded
