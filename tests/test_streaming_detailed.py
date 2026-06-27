# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""流式输出详细测试"""

from fastmind import Event


class TestStreamEventTypes:
    """流事件类型测试 — 验证 Event 结构契约"""

    def test_stream_chunk_event_structure(self):
        event = Event(type="stream.chunk", payload={"delta": "Hello"}, session_id="test")
        assert event.type == "stream.chunk"
        assert event.payload["delta"] == "Hello"
        assert event.session_id == "test"

    def test_stream_end_event_structure(self):
        event = Event(type="stream.end", payload={}, session_id="test")
        assert event.type == "stream.end"
        assert event.payload == {}
        assert event.session_id == "test"

    def test_stream_error_event_structure(self):
        event = Event(type="stream.error", payload={"error": "test error"}, session_id="test")
        assert event.type == "stream.error"
        assert "error" in event.payload
        assert event.session_id == "test"

    def test_stream_thinking_event_structure(self):
        event = Event(type="stream.thinking", payload={"delta": "thinking..."}, session_id="test")
        assert event.type == "stream.thinking"
        assert "delta" in event.payload
        assert event.session_id == "test"

    def test_stream_fragment_with_tool_calls(self):
        event = Event(
            type="stream.fragment",
            payload={
                "has_tool_calls": True,
                "tool_calls": [{"id": "call_1", "function": {"name": "test", "arguments": "{}"}}],
            },
            session_id="test",
        )
        assert event.type == "stream.fragment"
        assert event.payload["has_tool_calls"] is True
        assert len(event.payload["tool_calls"]) == 1
        assert event.session_id == "test"
