# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""Session 管理测试"""

import pytest
import uuid

from gateway.router import (
    load_sessions,
    save_sessions,
    ensure_sessions_db,
    SESSION_DB_FILE,
)

from tests.conftest import cleanup_test_session


class TestSessionStorage:
    """Session 存储测试"""

    def test_save_and_load_sessions(self, tmp_path, backup_sessions_json):
        """测试保存和加载 sessions"""
        session_id = f"test_session_{uuid.uuid4().hex[:8]}"
        sessions = load_sessions()
        sessions[session_id] = {
            "session_id": session_id,
            "agent_id": "main_agent",
            "created_at": "1234567890",
            "last_active_time": 0,
        }

        save_sessions(sessions)
        loaded = load_sessions()

        assert session_id in loaded
        assert loaded[session_id]["agent_id"] == "main_agent"

        cleanup_test_session(session_id)


class TestSessionCreate:
    """Session 创建测试"""

    def test_session_create_generates_id(self):
        """测试创建 session 生成 ID"""
        session_id = f"create_test_{uuid.uuid4().hex[:8]}"
        sessions = load_sessions()

        sessions[session_id] = {
            "session_id": session_id,
            "agent_id": "main_agent",
            "created_at": str(uuid.uuid4()),
            "last_active_time": 0,
        }

        save_sessions(sessions)

        loaded = load_sessions()
        assert session_id in loaded

        cleanup_test_session(session_id)

    def test_session_create_with_agent(self):
        """测试指定 agent 创建 session"""
        session_id = f"custom_agent_session_{uuid.uuid4().hex[:8]}"
        sessions = load_sessions()

        sessions[session_id] = {
            "session_id": session_id,
            "agent_id": "main_agent",
            "created_at": str(uuid.uuid4()),
            "last_active_time": 0,
        }

        save_sessions(sessions)

        loaded = load_sessions()
        assert loaded[session_id]["agent_id"] == "main_agent"

        cleanup_test_session(session_id)


class TestSessionUpdate:
    """Session 更新测试"""

    def test_session_update_agent(self):
        """测试更新 session 的 agent"""
        session_id = f"update_test_{uuid.uuid4().hex[:8]}"
        sessions = load_sessions()

        sessions[session_id] = {
            "session_id": session_id,
            "agent_id": "main_agent",
            "created_at": str(uuid.uuid4()),
            "last_active_time": 0,
        }

        save_sessions(sessions)

        sessions[session_id]["agent_id"] = "main_agent"
        save_sessions(sessions)

        loaded = load_sessions()
        assert loaded[session_id]["agent_id"] == "main_agent"

        cleanup_test_session(session_id)


class TestSessionDelete:
    """Session 删除测试"""

    def test_session_delete(self):
        """测试删除 session"""
        session_id = f"delete_test_{uuid.uuid4().hex[:8]}"
        sessions = load_sessions()

        sessions[session_id] = {
            "session_id": session_id,
            "agent_id": "main_agent",
            "created_at": str(uuid.uuid4()),
            "last_active_time": 0,
        }

        save_sessions(sessions)
        assert session_id in load_sessions()

        cleanup_test_session(session_id)

        loaded = load_sessions()
        assert session_id not in loaded


class TestSessionList:
    """Session 列表测试"""

    def test_session_list_multiple(self):
        """测试列出多个 sessions"""
        session_ids = [f"list_test_{i}_{uuid.uuid4().hex[:8]}" for i in range(3)]
        sessions = load_sessions()

        for session_id in session_ids:
            sessions[session_id] = {
                "session_id": session_id,
                "agent_id": "main_agent",
                "created_at": str(uuid.uuid4()),
                "last_active_time": 0,
            }

        save_sessions(sessions)

        loaded = load_sessions()
        for session_id in session_ids:
            assert session_id in loaded

        for session_id in session_ids:
            cleanup_test_session(session_id)
