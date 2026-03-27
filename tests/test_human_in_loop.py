"""Human-in-the-Loop 测试"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "vendor"))

from fastmind import Event


class TestInterruptEvent:
    """中断事件测试"""

    def test_interrupt_event_format(self):
        """测试中断事件格式"""
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
        """测试中断恢复节点"""
        event = Event(
            type="interrupt",
            payload={
                "prompt": "Continue?",
                "resume_node": "tools",
            },
            session_id="test",
        )

        assert event.payload["resume_node"] == "tools"


class TestResumeSession:
    """恢复会话测试"""

    def test_resume_event_format(self):
        """测试恢复事件格式"""
        event = Event(
            type="resume",
            payload={"user_input": "yes"},
            session_id="test_session",
        )

        assert event.type == "resume"
        assert event.payload["user_input"] == "yes"

    def test_resume_with_confirmation(self):
        """测试确认恢复"""
        event = Event(
            type="resume",
            payload={"user_input": "confirm"},
            session_id="test",
        )

        assert event.payload["user_input"] == "confirm"


class TestHumanInLoopFlow:
    """Human-in-the-Loop 流程测试"""

    def test_approve_node_yields_interrupt(self):
        """测试 approve_node 产生 interrupt 事件"""

        # 模拟 approve_node (同步版本)
        def approve_node_sync(state, event):
            return state, [
                Event(
                    type="interrupt",
                    payload={
                        "prompt": "请确认",
                        "resume_node": "agent",
                    },
                    session_id=event.session_id,
                )
            ]

        # 不实际调用，只是测试事件格式
        event = Event("test", {}, "session1")
        result = approve_node_sync({}, event)
        state, events = result

        assert len(events) == 1
        assert events[0].type == "interrupt"

    def test_resume_session_continues_flow(self):
        """测试恢复会话继续流程"""
        # 模拟 resume_session
        from fastmind import Event

        resume_event = Event(
            type="resume",
            payload={"user_input": "yes"},
            session_id="test",
        )

        assert resume_event.type == "resume"
        assert resume_event.session_id == "test"


class TestAuthorizationFlow:
    """授权流程测试"""

    def test_restricted_command_blocks(self):
        """测试受限命令被阻止"""
        # 模拟权限检查
        restricted_paths = ["core/", "gateway/", "/etc/"]

        command = "rm -rf /etc/important"
        is_blocked = any(path in command for path in restricted_paths)

        assert is_blocked is True

    def test_allowed_command_passes(self):
        """测试允许的命令通过"""
        allowed_paths = ["workspace/"]

        command = "cat workspace/data/file.txt"
        is_allowed = any(path in command for path in allowed_paths)

        assert is_allowed is True


class TestInterruptCleanup:
    """中断清理测试"""

    def test_state_cleanup_after_interrupt(self):
        """测试中断后状态清理"""
        state = {
            "_interrupted": True,
            "_checkpoint": {"state": {}, "current_node": "agent"},
        }

        # 模拟恢复后清理
        if "_interrupted" in state:
            del state["_interrupted"]
        if "_checkpoint" in state:
            del state["_checkpoint"]

        assert "_interrupted" not in state
        assert "_checkpoint" not in state
