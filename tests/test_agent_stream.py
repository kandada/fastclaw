# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""fastclaw_agent 流式输出 message_id 贯穿 & 用户消息去重 专项测试

覆盖接口层重构引入的改动：
- app.py: 所有 stream.* 输出事件携带 message_id
- app.py: user 消息改用 message_id 精确去重（连续相同内容不丢失、tool 循环不重复）
"""

import asyncio
import importlib
from types import SimpleNamespace

import pytest

from fastmind import Event

from core.app import fastclaw_agent

# 注意：`import core.app as app_mod` 会被 core/__init__.py 的 `from core.app import app`
# 覆盖成 FastMind 实例，必须用 import_module 获取真实模块对象。
app_mod = importlib.import_module("core.app")


# ---------------------------------------------------------------------------
# Mock LLM 客户端
# ---------------------------------------------------------------------------
class MockDelta:
    def __init__(self, content=None, reasoning=None, tool_calls=None):
        self.content = content
        self.reasoning_content = reasoning
        self.tool_calls = tool_calls


class MockToolCall:
    def __init__(self, index, tc_id, name, arguments):
        self.index = index
        self.id = tc_id
        self.function = SimpleNamespace(name=name, arguments=arguments)


class MockChunk:
    def __init__(self, delta):
        self.choices = [SimpleNamespace(delta=delta)]


class MockStream:
    def __init__(self, chunks):
        self._chunks = chunks
        # 直接在构造时初始化迭代器：_aiter_with_timeout 直接调用 __anext__ 而不调用 __aiter__
        self._it = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class MockCompletions:
    def __init__(self, chunks=None, error=None):
        self._chunks = chunks or []
        self._error = error

    async def create(self, **kwargs):
        if self._error is not None:
            raise self._error
        return MockStream(self._chunks)


class MockLLM:
    def __init__(self, chunks=None, error=None):
        self.chat = SimpleNamespace(completions=MockCompletions(chunks, error))


class MockQueue:
    """收集 output_queue.put_nowait 的事件"""

    def __init__(self):
        self.events = []

    def put_nowait(self, event):
        self.events.append(event)


async def _noop(*args, **kwargs):
    return None


def _make_state(session_id="s1", messages=None):
    return {
        "_session_id": session_id,
        "_output_queue": MockQueue(),
        "_agent_config": {"llm": {"model": "test-model"}, "context": {}},
        "_personality": "",
        "messages": messages if messages is not None else [],
    }


@pytest.fixture(autouse=True)
def _mock_llm_and_save(monkeypatch):
    """统一 mock LLM 客户端与消息落盘，避免真实网络/磁盘写入"""
    monkeypatch.setattr(app_mod, "_get_llm_client", lambda cfg: MockLLM())
    monkeypatch.setattr(app_mod, "_save_messages_async", _noop)


# ---------------------------------------------------------------------------
# message_id 贯穿
# ---------------------------------------------------------------------------
class TestAgentMessageId:
    def test_chunk_thinking_end_carry_message_id(self):
        chunks = [
            MockChunk(MockDelta(reasoning="think ")),
            MockChunk(MockDelta(content="hello")),
            MockChunk(MockDelta(content=" world")),
        ]
        state = _make_state()
        app_mod._get_llm_client = lambda cfg: MockLLM(chunks=chunks)

        asyncio.run(fastclaw_agent(
            state, Event("user.message", {"text": "hi", "message_id": "msg_abc"}, "s1")
        ))

        q = state["_output_queue"]
        types = [e.type for e in q.events]
        assert "stream.thinking" in types
        assert "stream.chunk" in types
        assert types[-1] == "stream.end"
        # 所有事件都携带 message_id
        for e in q.events:
            assert e.payload.get("message_id") == "msg_abc", e.type

    def test_fragment_carries_message_id_when_tool_calls(self):
        chunks = [
            MockChunk(MockDelta(tool_calls=[
                MockToolCall(0, "c1", "run_shell", '{"command": "ls"}'),
            ])),
        ]
        state = _make_state()
        app_mod._get_llm_client = lambda cfg: MockLLM(chunks=chunks)

        asyncio.run(fastclaw_agent(
            state, Event("user.message", {"text": "ls", "message_id": "msg_tool"}, "s1")
        ))

        q = state["_output_queue"]
        fragment = [e for e in q.events if e.type == "stream.fragment"]
        assert fragment, "应发出 stream.fragment 事件"
        assert fragment[0].payload["message_id"] == "msg_tool"
        assert fragment[0].payload["has_tool_calls"] is True

    def test_error_carries_message_id(self):
        state = _make_state()
        app_mod._get_llm_client = lambda cfg: MockLLM(error=RuntimeError("boom"))

        asyncio.run(fastclaw_agent(
            state, Event("user.message", {"text": "hi", "message_id": "msg_err"}, "s1")
        ))

        q = state["_output_queue"]
        err = [e for e in q.events if e.type == "stream.error"]
        assert err, "应发出 stream.error 事件"
        assert err[0].payload["message_id"] == "msg_err"


# ---------------------------------------------------------------------------
# user 消息 message_id 去重
# ---------------------------------------------------------------------------
class TestAgentUserMessageDedup:
    def _run(self, state, text, msg_id):
        chunks = [MockChunk(MockDelta(content="ok"))]
        app_mod._get_llm_client = lambda cfg: MockLLM(chunks=chunks)
        asyncio.run(fastclaw_agent(
            state, Event("user.message", {"text": text, "message_id": msg_id}, "s1")
        ))

    def test_consecutive_same_content_not_lost(self):
        """连续两条相同内容的消息（不同 message_id）不应被去重丢失"""
        state = _make_state()
        self._run(state, "hi", "msg_1")
        self._run(state, "hi", "msg_2")

        user_msgs = [m for m in state["messages"] if m.get("role") == "user"]
        assert len(user_msgs) == 2, f"相同内容的两条消息都应保留，实际 {len(user_msgs)} 条"
        assert user_msgs[0]["content"] == "hi"
        assert user_msgs[1]["content"] == "hi"

    def test_tool_loop_same_message_not_duplicated(self):
        """同一 message_id 的多次调用（agent↔tools 循环）不应重复追加 user 消息"""
        state = _make_state()
        self._run(state, "do task", "msg_1")
        # 模拟 tool 循环：同一事件再次进入 agent
        self._run(state, "do task", "msg_1")

        user_msgs = [m for m in state["messages"] if m.get("role") == "user"]
        assert len(user_msgs) == 1

    def test_no_message_id_falls_back_to_content_dedup(self):
        """无 message_id 的旧渠道：退回 content 去重（不重复追加）"""
        state = _make_state()
        self._run(state, "hi", None)  # 无 message_id
        self._run(state, "hi", None)
        user_msgs = [m for m in state["messages"] if m.get("role") == "user"]
        assert len(user_msgs) == 1
