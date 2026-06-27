# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""ReAct 循环测试"""

import pytest
import asyncio

from core.app import route
from fastmind import Event


class TestReActMessages:
    """ReAct 消息测试"""

    def test_messages_append_user(self):
        messages = []
        messages.append({"role": "user", "content": "Hello"})
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"

    def test_messages_append_assistant(self):
        messages = []
        messages.append({"role": "assistant", "content": "Hi there!"})
        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"

    def test_messages_append_tool(self):
        messages = []
        messages.append({
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "[run_shell]: file1.txt\nfile2.txt",
        })
        assert len(messages) == 1
        assert messages[0]["role"] == "tool"
        assert "run_shell" in messages[0]["content"]

    def test_messages_conversation_flow(self):
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
        state = {
            "_session_id": "test",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        assert len(state["messages"]) == 1
        assert state["messages"][0]["role"] == "user"

    def test_state_after_tool_calls(self):
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
        assert "tool_calls" not in state

    def test_state_end_marker(self):
        state = {
            "_session_id": "test",
            "_end": True,
        }
        assert state["_end"] is True


class TestReActCycle:
    """ReAct 循环完整测试"""

    def test_complete_cycle_user_to_end(self):
        state = {"_session_id": "test", "messages": []}
        event = Event("user.message", {"text": "Hello"}, "test")
        state["messages"].append({"role": "user", "content": "Hello"})
        assert route(state, event) is None

    def test_complete_cycle_with_tool(self):
        state = {
            "_session_id": "test",
            "messages": [{"role": "user", "content": "List files"}],
        }
        event = Event("user.message", {"text": "List files"}, "test")

        state["tool_calls"] = [{
            "id": "call_1",
            "function": {"name": "run_shell", "arguments": '{"command": "ls"}'},
        }]
        assert route(state, event) == "tools"

        state["tool_results"] = [
            {"tool_call_id": "call_1", "tool_name": "run_shell", "result": "file1.txt"}
        ]
        del state["tool_calls"]
        assert route(state, event) is None

    def test_multiple_tool_calls_cycle(self):
        state = {
            "_session_id": "test",
            "messages": [{"role": "user", "content": "Check files and count lines"}],
        }
        event = Event("user.message", {"text": "Check files and count lines"}, "test")

        state["tool_calls"] = [{
            "id": "call_1",
            "function": {"name": "run_shell", "arguments": '{"command": "ls"}'},
        }]
        assert route(state, event) == "tools"

        state["tool_results"] = [{
            "tool_call_id": "call_1",
            "tool_name": "run_shell",
            "result": "file1.txt file2.txt",
        }]
        del state["tool_calls"]
        state["messages"].append({
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "[run_shell]: file1.txt file2.txt",
        })

        state["tool_calls"] = [{
            "id": "call_2",
            "function": {"name": "run_shell", "arguments": '{"command": "wc -l file1.txt"}'},
        }]
        assert route(state, event) == "tools"

        state["tool_results"] = [{
            "tool_call_id": "call_2",
            "tool_name": "run_shell",
            "result": "42 file1.txt",
        }]
        del state["tool_calls"]
        state["messages"].append({"role": "assistant", "content": "file1.txt has 42 lines."})
        assert route(state, event) is None
