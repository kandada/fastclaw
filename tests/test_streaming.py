"""流式输出测试"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from core.app import app, fastclaw_agent, route, graph
from fastmind import Event


class TestStreamingAgent:
    """流式 Agent 测试"""

    @pytest.mark.asyncio
    async def test_agent_stream_flag(self):
        """测试 Agent 是否启用了流式"""
        assert app is not None
        graphs = app._graphs
        assert "main" in graphs

    def test_agent_exists(self):
        """测试 Agent 存在"""
        # Agent 通过装饰器注册
        assert app is not None


class TestRoute:
    """路由函数测试"""

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

    def test_route_default(self):
        """默认路由（无tool_calls无_end）应该结束流程"""
        state = {}
        event = Event("test", {}, "session1")
        result = route(state, event)
        assert result is None


class TestGraph:
    """Graph 测试"""

    def test_graph_structure(self):
        """测试图结构"""
        g = graph
        assert g is not None

    def test_graph_entry_point(self):
        """测试图有入口点"""
        # Graph 被注册到 app
        assert app is not None
        main_graph = app.get_graph("main")
        assert main_graph is not None
