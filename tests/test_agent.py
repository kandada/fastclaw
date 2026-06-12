"""Agent 和 Route 函数测试"""

import pytest
import asyncio

from core.app import route, app
from fastmind import Event


class TestRouteFunction:
    """Route 函数测试"""

    def test_route_with_tool_calls(self):
        state = {"tool_calls": [{"id": "1", "function": {"name": "test"}}]}
        event = Event("test", {}, "session1")
        assert route(state, event) == "tools"

    def test_route_with_end(self):
        state = {"_end": True}
        event = Event("test", {}, "session1")
        assert route(state, event) == "__end__"

    def test_route_first_time(self):
        state = {}
        event = Event("test", {}, "session1")
        assert route(state, event) is None

    def test_route_continues_after_first(self):
        state = {"_agent_started": True}
        event = Event("test", {}, "session1")
        assert route(state, event) is None

    def test_route_prefers_tool_calls_over_end(self):
        state = {"tool_calls": [{"id": "1"}], "_end": True}
        event = Event("test", {}, "session1")
        assert route(state, event) == "tools"

    def test_route_prefers_end_over_continue(self):
        state = {"_end": True, "_agent_started": True}
        event = Event("test", {}, "session1")
        assert route(state, event) == "__end__"


class TestRouteEdgeCases:
    """Route 边界情况测试"""

    def test_route_empty_state(self):
        state = {}
        event = Event("test", {}, "session1")
        assert route(state, event) is None

    def test_route_none_values(self):
        state = {"tool_calls": None, "_end": None, "_agent_started": None}
        event = Event("test", {}, "session1")
        assert route(state, event) is None

    def test_route_partial_state(self):
        state = {"tool_calls": []}
        event = Event("test", {}, "session1")
        assert route(state, event) is None


class TestAgentState:
    """Agent 状态测试"""

    def test_state_messages_initialization(self):
        state = {}
        state.setdefault("messages", [])
        assert state["messages"] == []

    def test_state_agent_config(self):
        state = {}
        agent_config = {"name": "test_agent", "llm": {"model": "test"}}
        state["_agent_config"] = agent_config
        assert state["_agent_config"]["name"] == "test_agent"


class TestToolCalls:
    """Tool Calls 测试"""

    def test_tool_calls_format(self):
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
        tool_results = [
            {
                "tool_call_id": "call_001",
                "tool_name": "run_shell",
                "result": "file1.txt\nfile2.txt",
            }
        ]
        state = {"tool_results": tool_results}
        assert state["tool_results"][0]["tool_name"] == "run_shell"


class TestStreamingAgent:
    """流式 Agent 测试"""

    def test_agent_stream_flag(self):
        assert app is not None
        graphs = app._graphs
        assert "main" in graphs

    def test_agent_exists(self):
        assert app is not None
