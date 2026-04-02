"""Graph 节点测试"""

import pytest
import asyncio

from core.app import (
    app,
    route,
    graph,
    tool_node,
)
from fastmind import Event


class TestGraphStructure:
    """图结构测试"""

    def test_graph_is_registered(self):
        """图已注册"""
        assert app is not None
        assert "main" in app._graphs

    def test_graph_retrievable(self):
        """图可获取"""
        main_graph = app.get_graph("main")
        assert main_graph is not None

    def test_graph_has_nodes(self):
        """图有节点"""
        assert graph is not None

        assert graph.get_node("agent") is not None
        assert graph.get_node("tools") is not None

    def test_graph_entry_point(self):
        """图有入口点"""
        assert graph.entry_point == "agent"


class TestGraphNodes:
    """图节点测试"""

    def test_agent_node_exists(self):
        """agent 节点存在"""
        node = graph.get_node("agent")
        assert node is not None

    def test_tools_node_exists(self):
        """tools 节点存在"""
        node = graph.get_node("tools")
        assert node is not None

    def test_tools_node_is_tool_node(self):
        """tools 节点是 ToolNode"""
        node = graph.get_node("tools")
        assert isinstance(node, type(tool_node)) or hasattr(node, "tools")

    def test_agent_node_is_callable(self):
        """agent 节点可调用"""
        node = graph.get_node("agent")
        assert callable(node) or hasattr(node, "execute")


class TestGraphEdges:
    """图边测试"""

    def test_graph_has_edges(self):
        """图有边"""
        state = {"tool_calls": [{"id": "1"}]}
        event = Event("test", {}, "s1")

        next_node = graph.get_next_node("agent", state, event)
        assert next_node == "tools"

        next_node = graph.get_next_node("tools", {}, event)
        assert next_node == "agent"

    def test_tools_to_agent_edge(self):
        """tools -> agent 边存在"""
        state = {}
        event = Event("test", {}, "s1")
        next_node = graph.get_next_node("tools", state, event)
        assert next_node == "agent"


class TestGraphConditionalRouting:
    """图条件路由测试"""

    def test_route_returns_tools_for_tool_calls(self):
        """route 为 tool_calls 返回 tools"""
        state = {"tool_calls": [{"id": "1", "function": {"name": "test"}}]}
        event = Event("test", {}, "s1")

        result = route(state, event)

        assert result == "tools"

    def test_route_returns_end_for_end_marker(self):
        """route 为 _end 返回 __end__"""
        state = {"_end": True}
        event = Event("test", {}, "s1")

        result = route(state, event)

        assert result == "__end__"

    def test_route_returns_none_for_default(self):
        """route 无特殊标记返回 None"""
        state = {}
        event = Event("test", {}, "s1")

        result = route(state, event)

        assert result is None


class TestGraphTraversal:
    """图遍历测试"""

    def test_get_next_node_with_tool_calls(self):
        """有 tool_calls 时获取下一步为 tools"""
        state = {"tool_calls": [{"id": "1"}]}
        event = Event("test", {}, "s1")

        next_node = graph.get_next_node("agent", state, event)

        assert next_node == "tools"

    def test_get_next_node_without_tool_calls(self):
        """无 tool_calls 时获取下一步为 None（结束）"""
        state = {"messages": []}
        event = Event("test", {}, "s1")

        next_node = graph.get_next_node("agent", state, event)

        assert next_node is None

    def test_get_next_node_from_tools(self):
        """从 tools 节点获取下一步"""
        state = {}
        event = Event("test", {}, "s1")

        next_node = graph.get_next_node("tools", state, event)

        assert next_node == "agent"


class TestGraphExecution:
    """图执行测试"""

    @pytest.mark.asyncio
    async def test_agent_node_executable(self):
        """agent 节点可执行"""
        node = graph.get_node("agent")

        assert node is not None
        assert asyncio.iscoroutinefunction(node) or hasattr(node, "execute")

    @pytest.mark.asyncio
    async def test_tools_node_executable(self):
        """tools 节点可执行"""
        node = graph.get_node("tools")

        assert node is not None


class TestGraphIntegration:
    """图集成测试"""

    def test_full_flow_without_tools(self):
        """完整流程：无工具调用"""
        state = {"_session_id": "test", "messages": []}
        event = Event("user.message", {"text": "Hello"}, "test")

        state["messages"].append({"role": "user", "content": "Hello"})

        result = route(state, event)
        assert result is None

    def test_full_flow_with_tools(self):
        """完整流程：有工具调用"""
        state = {"_session_id": "test", "messages": []}
        event = Event("user.message", {"text": "Run ls"}, "test")

        state["messages"].append({"role": "user", "content": "Run ls"})

        state["tool_calls"] = [
            {"id": "call_1", "function": {"name": "run_shell", "arguments": "{}"}}
        ]
        result = route(state, event)
        assert result == "tools"

        state["tool_results"] = [
            {"tool_call_id": "call_1", "tool_name": "run_shell", "result": "files"}
        ]
        del state["tool_calls"]
        state["messages"].append(
            {"role": "tool", "tool_call_id": "call_1", "content": "[run_shell]: files"}
        )

        result = route(state, event)
        assert result is None


class TestGraphState:
    """图状态测试"""

    def test_state_has_required_keys(self):
        """状态有必需键"""
        state = {
            "_session_id": "test",
            "_output_queue": asyncio.Queue(),
            "messages": [],
        }

        assert "_session_id" in state
        assert "_output_queue" in state
        assert "messages" in state

    def test_state_messages_list(self):
        """状态消息是列表"""
        state = {"messages": []}

        assert isinstance(state["messages"], list)

    def test_state_tool_calls_format(self):
        """状态 tool_calls 格式"""
        state = {
            "tool_calls": [
                {"id": "call_1", "function": {"name": "test", "arguments": "{}"}}
            ]
        }

        assert isinstance(state["tool_calls"], list)
        assert "function" in state["tool_calls"][0]

    def test_state_tool_results_format(self):
        """状态 tool_results 格式"""
        state = {
            "tool_results": [
                {"tool_call_id": "call_1", "tool_name": "test", "result": "output"}
            ]
        }

        assert isinstance(state["tool_results"], list)
        assert "result" in state["tool_results"][0]


class TestGraphReAct:
    """Graph ReAct 模式测试"""

    def test_react_loop_single_turn(self):
        """ReAct 单轮对话"""
        state = {
            "_session_id": "test",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        event = Event("user.message", {"text": "Hello"}, "test")

        result = route(state, event)

        assert result is None

    def test_react_loop_with_tool_use(self):
        """ReAct 工具使用"""
        state = {
            "_session_id": "test",
            "messages": [{"role": "user", "content": "List files"}],
        }
        event = Event("user.message", {"text": "List files"}, "test")

        state["tool_calls"] = [
            {
                "id": "call_1",
                "function": {"name": "run_shell", "arguments": '{"command": "ls"}'},
            }
        ]

        next_node = graph.get_next_node("agent", state, event)
        assert next_node == "tools"

        state["tool_results"] = [
            {"tool_call_id": "call_1", "tool_name": "run_shell", "result": "file1.txt"}
        ]
        del state["tool_calls"]

        next_node = graph.get_next_node("tools", state, event)
        assert next_node == "agent"

    def test_react_multiple_tool_calls(self):
        """ReAct 多工具调用"""
        state = {
            "_session_id": "test",
            "messages": [{"role": "user", "content": "Check files and get time"}],
        }
        event = Event("user.message", {"text": "Check files and get time"}, "test")

        state["tool_calls"] = [
            {
                "id": "call_1",
                "function": {"name": "run_shell", "arguments": '{"command": "ls"}'},
            }
        ]

        next_node = graph.get_next_node("agent", state, event)
        assert next_node == "tools"

        state["tool_results"] = [
            {"tool_call_id": "call_1", "tool_name": "run_shell", "result": "files"}
        ]
        del state["tool_calls"]

        state["tool_calls"] = [
            {
                "id": "call_2",
                "function": {
                    "name": "run_skills",
                    "arguments": '{"skill_name": "current_time"}',
                },
            }
        ]

        next_node = graph.get_next_node("tools", state, event)
        assert next_node == "agent"

        next_node = graph.get_next_node("agent", state, event)
        assert next_node == "tools"
