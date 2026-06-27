# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""Graph 节点测试"""

import pytest
import asyncio

from core.app import app, route, graph, tool_node
from fastmind import Event


class TestGraphStructure:
    """图结构测试"""

    def test_graph_is_registered(self):
        assert app is not None
        assert "main" in app._graphs

    def test_graph_retrievable(self):
        main_graph = app.get_graph("main")
        assert main_graph is not None

    def test_graph_has_nodes(self):
        assert graph is not None
        assert graph.get_node("agent") is not None
        assert graph.get_node("tools") is not None

    def test_graph_entry_point(self):
        assert graph.entry_point == "agent"


class TestGraphNodes:
    """图节点测试"""

    def test_agent_node_exists(self):
        node = graph.get_node("agent")
        assert node is not None

    def test_tools_node_exists(self):
        node = graph.get_node("tools")
        assert node is not None

    def test_tools_node_is_tool_node(self):
        node = graph.get_node("tools")
        assert isinstance(node, type(tool_node)) or hasattr(node, "tools")

    def test_agent_node_is_callable(self):
        node = graph.get_node("agent")
        assert callable(node) or hasattr(node, "execute")


class TestGraphTraversal:
    """图遍历测试"""

    def test_get_next_node_with_tool_calls(self):
        state = {"tool_calls": [{"id": "1"}]}
        event = Event("test", {}, "s1")
        next_node = graph.get_next_node("agent", state, event)
        assert next_node == "tools"

    def test_get_next_node_without_tool_calls(self):
        state = {"messages": []}
        event = Event("test", {}, "s1")
        next_node = graph.get_next_node("agent", state, event)
        assert next_node is None

    def test_get_next_node_from_tools(self):
        state = {}
        event = Event("test", {}, "s1")
        next_node = graph.get_next_node("tools", state, event)
        assert next_node == "agent"

    def test_route_returns_tools_for_tool_calls(self):
        state = {"tool_calls": [{"id": "1", "function": {"name": "test"}}]}
        event = Event("test", {}, "s1")
        assert route(state, event) == "tools"

    def test_route_returns_end_for_end_marker(self):
        state = {"_end": True}
        event = Event("test", {}, "s1")
        assert route(state, event) == "__end__"

    def test_route_returns_none_for_default(self):
        state = {}
        event = Event("test", {}, "s1")
        assert route(state, event) is None


class TestGraphExecution:
    """图执行测试"""

    @pytest.mark.asyncio
    async def test_agent_node_executable(self):
        node = graph.get_node("agent")
        assert node is not None
        assert asyncio.iscoroutinefunction(node) or hasattr(node, "execute")

    @pytest.mark.asyncio
    async def test_tools_node_executable(self):
        node = graph.get_node("tools")
        assert node is not None
