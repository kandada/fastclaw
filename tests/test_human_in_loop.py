# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""Human-in-the-Loop 测试"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "vendor"))

from fastmind import Event


class TestInterruptEvent:
    """中断事件测试 — 验证 Event 契约"""

    def test_interrupt_event_format(self):
        event = Event(
            type="interrupt",
            payload={
                "prompt": "确认要执行此操作吗？",
                "resume_node": "agent",
                "cancel_node": None,
            },
            session_id="test_session",
        )
        assert event.type == "interrupt"
        assert "prompt" in event.payload
        assert "resume_node" in event.payload

    def test_interrupt_resume_node(self):
        event = Event(
            type="interrupt",
            payload={"prompt": "Continue?", "resume_node": "tools"},
            session_id="test",
        )
        assert event.payload["resume_node"] == "tools"


class TestResumeEvent:
    """恢复事件测试 — 验证 Event 契约"""

    def test_resume_event_format(self):
        event = Event(
            type="resume",
            payload={"user_input": "yes"},
            session_id="test_session",
        )
        assert event.type == "resume"
        assert event.payload["user_input"] == "yes"

    def test_resume_with_confirmation(self):
        event = Event(
            type="resume",
            payload={"user_input": "confirm"},
            session_id="test",
        )
        assert event.payload["user_input"] == "confirm"


class TestInterruptState:
    """中断状态管理测试"""

    def test_state_has_interrupt_flag(self):
        state = {"_interrupted": True, "_checkpoint": {"current_node": "agent"}}
        assert "_interrupted" in state
        assert state["_checkpoint"]["current_node"] == "agent"

    def test_cleanup_removes_interrupt_fields(self):
        state = {
            "_interrupted": True,
            "_checkpoint": {"state": {}, "current_node": "agent"},
        }
        if "_interrupted" in state:
            del state["_interrupted"]
        if "_checkpoint" in state:
            del state["_checkpoint"]
        assert "_interrupted" not in state
        assert "_checkpoint" not in state
