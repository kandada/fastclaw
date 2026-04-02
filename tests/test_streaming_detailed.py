"""流式输出详细测试"""

import pytest
import asyncio

from fastmind import Event


class TestStreamingDetails:
    """流式输出细节测试"""

    @pytest.mark.asyncio
    async def test_streaming_yields_multiple_chunks(self):
        """测试流式输出产生多个 chunk"""
        chunks_content = ["Hello", " ", "World", "!"]

        class MockDelta:
            def __init__(self, content):
                self.content = content
                self.tool_calls = None

        class MockChoice:
            def __init__(self, delta):
                self.delta = delta
                self.index = 0

        class MockChunk:
            def __init__(self, delta_content):
                self.choices = [MockChoice(MockDelta(delta_content))]

        async def async_gen():
            for chunk_text in chunks_content:
                yield MockChunk(chunk_text)

        collected = []
        async for chunk in async_gen():
            if chunk.choices[0].delta.content:
                collected.append(chunk.choices[0].delta.content)

        assert len(collected) == 4
        assert "".join(collected) == "Hello World!"

    @pytest.mark.asyncio
    async def test_streaming_empty_content_no_chunk(self):
        """测试空 content 不发送 chunk"""
        chunks_content = ["Hello", "", "World", ""]

        collected = []
        for chunk_text in chunks_content:
            if chunk_text:
                collected.append(chunk_text)

        assert len(collected) == 2
        assert "".join(collected) == "HelloWorld"

    @pytest.mark.asyncio
    async def test_streaming_with_tool_calls_in_chunks(self):
        """测试流式响应中包含 tool_calls"""
        mock_deltas = [
            ("Hello ", None),
            ("I'll run a command", None),
            (
                "",
                [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "run_shell",
                            "arguments": '{"command": "ls"}',
                        },
                    }
                ],
            ),
        ]

        full_content = ""
        tool_calls = []

        for content, tc in mock_deltas:
            if content:
                full_content += content
            if tc:
                tool_calls.extend(tc)

        assert full_content == "Hello I'll run a command"
        assert len(tool_calls) == 1
        assert tool_calls[0]["function"]["name"] == "run_shell"


class TestStreamingQueue:
    """流式队列测试"""

    def test_output_queue_in_state(self):
        """测试 state 中包含 output_queue"""
        state = {"_output_queue": asyncio.Queue(), "_session_id": "test"}

        assert "_output_queue" in state
        assert hasattr(state["_output_queue"], "put_nowait")

    @pytest.mark.asyncio
    async def test_put_event_to_queue(self):
        """测试向队列放入事件"""
        queue = asyncio.Queue()

        event = Event(type="stream.chunk", payload={"delta": "test"}, session_id="test")
        queue.put_nowait(event)

        got = await queue.get()
        assert got.type == "stream.chunk"
        assert got.payload["delta"] == "test"

    @pytest.mark.asyncio
    async def test_stream_end_event(self):
        """测试流结束事件"""
        queue = asyncio.Queue()

        end_event = Event(type="stream.end", payload={}, session_id="test")
        queue.put_nowait(end_event)

        got = await queue.get()
        assert got.type == "stream.end"


class TestStreamingConcurrency:
    """并发流式测试"""

    @pytest.mark.asyncio
    async def test_concurrent_stream_events(self):
        """测试并发流式事件"""
        queue = asyncio.Queue()
        results = []

        async def producer():
            for i in range(5):
                event = Event(
                    type="stream.chunk", payload={"delta": str(i)}, session_id="test"
                )
                await queue.put(event)
                await asyncio.sleep(0.01)

        async def consumer():
            count = 0
            while count < 5:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    results.append(event.payload["delta"])
                    count += 1
                except asyncio.TimeoutError:
                    break

        await asyncio.gather(producer(), consumer())

        assert len(results) == 5
        assert results == ["0", "1", "2", "3", "4"]


class TestStreamingError:
    """流式错误处理测试"""

    @pytest.mark.asyncio
    async def test_stream_error_event(self):
        """测试错误事件"""
        queue = asyncio.Queue()

        error_event = Event(
            type="stream.error",
            payload={"error": "Connection timeout"},
            session_id="test",
        )
        await queue.put(error_event)

        got = await queue.get()
        assert got.type == "stream.error"
        assert got.payload["error"] == "Connection timeout"

    @pytest.mark.asyncio
    async def test_stream_error_format(self):
        """测试错误事件格式"""
        error_event = Event(
            type="stream.error",
            payload={"error": "Some error message"},
            session_id="session_123",
        )

        assert error_event.type == "stream.error"
        assert "error" in error_event.payload
        assert error_event.session_id == "session_123"


class TestStreamEventTypes:
    """流事件类型测试"""

    def test_stream_chunk_event_structure(self):
        """测试 stream.chunk 事件结构"""
        event = Event(
            type="stream.chunk", payload={"delta": "Hello"}, session_id="test"
        )

        assert event.type == "stream.chunk"
        assert event.payload["delta"] == "Hello"
        assert event.session_id == "test"

    def test_stream_end_event_structure(self):
        """测试 stream.end 事件结构"""
        event = Event(type="stream.end", payload={}, session_id="test")

        assert event.type == "stream.end"
        assert event.payload == {}
        assert event.session_id == "test"

    def test_stream_error_event_structure(self):
        """测试 stream.error 事件结构"""
        event = Event(
            type="stream.error", payload={"error": "test error"}, session_id="test"
        )

        assert event.type == "stream.error"
        assert "error" in event.payload
        assert event.session_id == "test"
