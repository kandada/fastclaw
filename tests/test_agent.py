"""Agent 和 Route 函数测试"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "vendor"))

from fastmind import Event

from core.app import route


class TestRouteFunction:
    """Route 函数测试"""

    def test_route_with_tool_calls(self):
        """有 tool_calls 时路由到 tools"""
        state = {"tool_calls": [{"id": "1", "function": {"name": "test"}}]}
        event = Event("test", {}, "session1")
        result = route(state, event)
        assert result == "tools"

    def test_route_with_end(self):
        """有 _end 时路由到 __end__"""
        state = {"_end": True}
        event = Event("test", {}, "session1")
        result = route(state, event)
        assert result == "__end__"

    def test_route_first_time(self):
        """首次路由（无tool_calls无_end）返回None结束流程"""
        state = {}
        event = Event("test", {}, "session1")
        result = route(state, event)
        assert result is None

    def test_route_continues_after_first(self):
        """无tool_calls无_end返回None"""
        state = {"_agent_started": True}
        event = Event("test", {}, "session1")
        result = route(state, event)
        assert result is None

    def test_route_prefers_tool_calls_over_end(self):
        """tool_calls 优先于 _end"""
        state = {"tool_calls": [{"id": "1"}], "_end": True}
        event = Event("test", {}, "session1")
        result = route(state, event)
        assert result == "tools"

    def test_route_prefers_end_over_continue(self):
        """_end 优先于继续循环"""
        state = {"_end": True, "_agent_started": True}
        event = Event("test", {}, "session1")
        result = route(state, event)
        assert result == "__end__"


class TestRouteEdgeCases:
    """Route 边界情况测试"""

    def test_route_empty_state(self):
        """空 state（无tool_calls无_end）返回None"""
        state = {}
        event = Event("test", {}, "session1")
        result = route(state, event)
        assert result is None

    def test_route_none_values(self):
        """值为 None（无tool_calls无_end）返回None"""
        state = {"tool_calls": None, "_end": None, "_agent_started": None}
        event = Event("test", {}, "session1")
        result = route(state, event)
        assert result is None

    def test_route_partial_state(self):
        """部分 state（空tool_calls列表，无_end）返回None"""
        state = {"tool_calls": []}  # 空列表是 falsy
        event = Event("test", {}, "session1")
        result = route(state, event)
        assert result is None


class TestAgentState:
    """Agent 状态测试"""

    def test_state_messages_initialization(self):
        """测试 messages 初始化"""
        state = {}
        state.setdefault("messages", [])
        assert state["messages"] == []

    def test_state_agent_config(self):
        """测试 agent_config 存储"""
        state = {}
        agent_config = {"name": "test_agent", "llm": {"model": "test"}}
        state["_agent_config"] = agent_config
        assert state["_agent_config"]["name"] == "test_agent"


class TestToolCalls:
    """Tool Calls 测试"""

    def test_tool_calls_format(self):
        """测试 tool_calls 格式"""
        tool_calls = [
            {
                "id": "call_001",
                "function": {
                    "name": "run_shell",
                    "arguments": '{"command": "ls"}',
                },
            }
        ]

        state = {"tool_calls": tool_calls}
        assert state["tool_calls"][0]["function"]["name"] == "run_shell"

    def test_tool_results_format(self):
        """测试 tool_results 格式"""
        tool_results = [
            {
                "tool_call_id": "call_001",
                "tool_name": "run_shell",
                "result": "file1.txt\nfile2.txt",
            }
        ]

        state = {"tool_results": tool_results}
        assert state["tool_results"][0]["tool_name"] == "run_shell"
