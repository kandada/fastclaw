"""ReAct 循环测试"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from core.app import app, fastclaw_agent, route, graph, tool_node
from fastmind import Event


class TestReActBasic:
    """ReAct 基础测试"""

    def test_route_with_tool_calls_routes_to_tools(self):
        """有 tool_calls 路由到 tools"""
        state = {
            "tool_calls": [
                {"id": "call_1", "function": {"name": "run_shell", "arguments": "{}"}}
            ]
        }
        event = Event("test", {}, "session1")
        result = route(state, event)
        assert result == "tools"

    def test_route_with_end_routes_to_end(self):
        """有 _end 路由到 __end__"""
        state = {"_end": True}
        event = Event("test", {}, "session1")
        result = route(state, event)
        assert result == "__end__"

    def test_route_without_tool_calls_or_end_returns_none(self):
        """无 tool_calls 无 _end 返回 None 结束"""
        state = {"messages": []}
        event = Event("test", {}, "session1")
        result = route(state, event)
        assert result is None


class TestReActFlow:
    """ReAct 流程测试"""

    def test_graph_has_two_nodes(self):
        """图包含 agent 和 tools 两个节点"""
        assert graph is not None

        # Graph 节点
        agent_node = graph.get_node("agent")
        tools_node = graph.get_node("tools")

        assert agent_node is not None
        assert tools_node is not None

    def test_graph_entry_point_is_agent(self):
        """图的入口点是 agent"""
        assert graph.entry_point == "agent"

    def test_graph_has_conditional_edges(self):
        """图有条件边"""
        # 验证图配置存在
        assert graph is not None
        # 通过 get_next_node 验证边存在
        state = {"tool_calls": [{"id": "1"}]}
        event = Event("test", {}, "s1")
        next_node = graph.get_next_node("agent", state, event)
        assert next_node == "tools"

    def test_tools_node_connected_to_agent(self):
        """tools 节点连接到 agent"""
        # 验证 tools 执行完后回到 agent
        state = {}
        event = Event("test", {}, "s1")
        next_node = graph.get_next_node("tools", state, event)
        assert next_node == "agent"


class TestReActToolCalls:
    """ReAct 工具调用测试"""

    def test_tool_calls_format_complete(self):
        """完整的 tool_calls 格式"""
        tool_calls = [
            {
                "id": "call_abc123",
                "type": "function",
                "function": {"name": "run_shell", "arguments": '{"command": "ls -la"}'},
            }
        ]

        state = {"tool_calls": tool_calls}

        assert "tool_calls" in state
        assert len(state["tool_calls"]) == 1
        assert state["tool_calls"][0]["function"]["name"] == "run_shell"

    def test_tool_calls_arguments_parsing(self):
        """tool_calls 参数解析"""
        tool_calls = [
            {
                "id": "call_1",
                "function": {
                    "name": "run_shell",
                    "arguments": '{"command": "cat file.txt"}',
                },
            }
        ]

        import json

        args = json.loads(tool_calls[0]["function"]["arguments"])

        assert args["command"] == "cat file.txt"

    def test_multiple_tool_calls(self):
        """多个 tool_calls"""
        tool_calls = [
            {"id": "call_1", "function": {"name": "run_shell", "arguments": "{}"}},
            {"id": "call_2", "function": {"name": "run_skills", "arguments": "{}"}},
        ]

        state = {"tool_calls": tool_calls}

        assert len(state["tool_calls"]) == 2


class TestReActToolResults:
    """ReAct 工具结果测试"""

    def test_tool_results_format(self):
        """tool_results 格式"""
        tool_results = [
            {
                "tool_call_id": "call_abc123",
                "tool_name": "run_shell",
                "result": "file1.txt\nfile2.txt\nfile3.txt",
            }
        ]

        state = {"tool_results": tool_results}

        assert "tool_results" in state
        assert state["tool_results"][0]["tool_name"] == "run_shell"
        assert "file1.txt" in state["tool_results"][0]["result"]

    def test_tool_results_chain_format(self):
        """工具结果链式格式"""
        tool_results = [
            {"tool_call_id": "call_1", "tool_name": "run_shell", "result": "output1"},
            {"tool_call_id": "call_2", "tool_name": "run_shell", "result": "output2"},
        ]

        state = {"tool_results": tool_results}

        assert len(state["tool_results"]) == 2


class TestReActMessages:
    """ReAct 消息测试"""

    def test_messages_append_user(self):
        """添加用户消息"""
        messages = []
        messages.append({"role": "user", "content": "Hello"})

        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"

    def test_messages_append_assistant(self):
        """添加助手消息"""
        messages = []
        messages.append({"role": "assistant", "content": "Hi there!"})

        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"

    def test_messages_append_tool(self):
        """添加工具结果消息"""
        messages = []
        messages.append(
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "[run_shell]: file1.txt\nfile2.txt",
            }
        )

        assert len(messages) == 1
        assert messages[0]["role"] == "tool"
        assert "run_shell" in messages[0]["content"]

    def test_messages_conversation_flow(self):
        """对话流程消息"""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "user", "content": "Run ls"},
            {"role": "assistant", "content": "I'll run that..."},
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "[run_shell]: file1.txt",
            },
            {"role": "assistant", "content": "I see file1.txt in the directory."},
        ]

        assert len(messages) == 6
        assert messages[0]["role"] == "user"
        assert messages[-1]["role"] == "assistant"


class TestReActStateTransitions:
    """ReAct 状态转换测试"""

    def test_state_initial(self):
        """初始状态"""
        state = {
            "_session_id": "test",
            "_output_queue": asyncio.Queue(),
            "messages": [],
        }

        assert "_session_id" in state
        assert "_output_queue" in state
        assert "messages" in state
        assert len(state["messages"]) == 0

    def test_state_after_user_message(self):
        """用户消息后的状态"""
        state = {
            "_session_id": "test",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        assert len(state["messages"]) == 1
        assert state["messages"][0]["role"] == "user"

    def test_state_after_tool_calls(self):
        """工具调用后的状态"""
        state = {
            "_session_id": "test",
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Running command..."},
            ],
            "tool_calls": [
                {"id": "call_1", "function": {"name": "run_shell", "arguments": "{}"}}
            ],
        }

        assert "tool_calls" in state
        assert state["tool_calls"][0]["function"]["name"] == "run_shell"

    def test_state_after_tool_results(self):
        """工具结果后的状态"""
        state = {
            "_session_id": "test",
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Running command..."},
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "content": "[run_shell]: output",
                },
            ],
            "tool_results": [
                {"tool_call_id": "call_1", "tool_name": "run_shell", "result": "output"}
            ],
        }

        assert "tool_results" in state
        # tool_results 被处理后应该删除
        assert "tool_calls" not in state

    def test_state_end_marker(self):
        """结束标记状态"""
        state = {
            "_session_id": "test",
            "_end": True,
        }

        assert state["_end"] is True


class TestReActCycle:
    """ReAct 循环完整测试"""

    def test_complete_cycle_user_to_end(self):
        """完整循环：用户 -> agent -> 结束"""
        # 1. 初始状态
        state = {"_session_id": "test", "messages": []}
        event = Event("user.message", {"text": "Hello"}, "test")

        # 2. 用户消息添加
        state["messages"].append({"role": "user", "content": "Hello"})

        # 3. route 检查（无 tool_calls）
        result = route(state, event)
        assert result is None  # 结束

    def test_complete_cycle_with_tool(self):
        """完整循环：用户 -> agent -> tools -> agent -> 结束"""
        # 1. 初始状态
        state = {
            "_session_id": "test",
            "messages": [{"role": "user", "content": "List files"}],
        }
        event = Event("user.message", {"text": "List files"}, "test")

        # 2. agent 决定调用工具
        state["tool_calls"] = [
            {
                "id": "call_1",
                "function": {"name": "run_shell", "arguments": '{"command": "ls"}'},
            }
        ]

        # 3. route 到 tools
        result = route(state, event)
        assert result == "tools"

        # 4. 工具执行后，tool_results 放入 state
        state["tool_results"] = [
            {"tool_call_id": "call_1", "tool_name": "run_shell", "result": "file1.txt"}
        ]
        del state["tool_calls"]

        # 5. route 回到 agent
        result = route(state, event)
        assert result is None  # 结束

    def test_multiple_tool_calls_cycle(self):
        """多工具调用循环"""
        state = {
            "_session_id": "test",
            "messages": [
                {"role": "user", "content": "Check files and count lines"},
            ],
        }
        event = Event("user.message", {"text": "Check files and count lines"}, "test")

        # 第一个工具调用
        state["tool_calls"] = [
            {
                "id": "call_1",
                "function": {"name": "run_shell", "arguments": '{"command": "ls"}'},
            }
        ]
        assert route(state, event) == "tools"

        # 工具1结果
        state["tool_results"] = [
            {
                "tool_call_id": "call_1",
                "tool_name": "run_shell",
                "result": "file1.txt file2.txt",
            }
        ]
        del state["tool_calls"]
        state["messages"].append(
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "[run_shell]: file1.txt file2.txt",
            }
        )

        # 第二个工具调用
        state["tool_calls"] = [
            {
                "id": "call_2",
                "function": {
                    "name": "run_shell",
                    "arguments": '{"command": "wc -l file1.txt"}',
                },
            }
        ]
        assert route(state, event) == "tools"

        # 工具2结果
        state["tool_results"] = [
            {
                "tool_call_id": "call_2",
                "tool_name": "run_shell",
                "result": "42 file1.txt",
            }
        ]
        del state["tool_calls"]

        # 最终回复后结束
        state["messages"].append(
            {"role": "assistant", "content": "file1.txt has 42 lines."}
        )
        assert route(state, event) is None
