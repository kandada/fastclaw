"""Gateway与FastMindAPI集成测试"""

import pytest
import asyncio
import uuid
import sys
from pathlib import Path

pytestmark = pytest.mark.slow

sys.path.insert(0, str(Path(__file__).parent.parent / "vendor"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastmind import Event
from tests.conftest import cleanup_test_session


class TestBridgeAPI:
    """Bridge API 测试"""

    @pytest.mark.asyncio
    async def test_api_start(self, shared_api):
        assert shared_api is not None
        assert shared_api.app is not None

    @pytest.mark.asyncio
    async def test_push_event(self, shared_api, unique_session_id):
        event = Event("user.message", {"text": "hello"}, unique_session_id)
        session = await shared_api.push_event(unique_session_id, event)
        assert session is not None
        assert session.session_id == unique_session_id
        cleanup_test_session(unique_session_id)

    @pytest.mark.asyncio
    async def test_stream_events(self, shared_api, unique_session_id):
        event = Event("user.message", {"text": "hello"}, unique_session_id)
        await shared_api.push_event(unique_session_id, event)
        await asyncio.sleep(0.5)

        events = []
        async for ev in shared_api.stream_events(unique_session_id):
            events.append(ev)
            if ev.type in ("stream.end", "error"):
                break

        assert len(events) > 0
        cleanup_test_session(unique_session_id)

    @pytest.mark.asyncio
    async def test_get_state(self, shared_api, unique_session_id):
        event = Event("user.message", {"text": "hello"}, unique_session_id)
        await shared_api.push_event(unique_session_id, event)
        await asyncio.sleep(0.5)

        state = shared_api.get_state(unique_session_id)
        assert state is not None
        assert "messages" in state
        cleanup_test_session(unique_session_id)

    @pytest.mark.asyncio
    async def test_get_session(self, shared_api, unique_session_id):
        event = Event("user.message", {"text": "hello"}, unique_session_id)
        await shared_api.push_event(unique_session_id, event)
        retrieved = shared_api.get_session(unique_session_id)
        assert retrieved is not None
        assert retrieved.session_id == unique_session_id
        cleanup_test_session(unique_session_id)

    @pytest.mark.asyncio
    async def test_list_sessions(self, shared_api, main_agent_id):
        session_ids = [f"list_test_{i}_{uuid.uuid4().hex[:8]}" for i in range(2)]
        for i, session_id in enumerate(session_ids):
            event = Event("user.message", {"text": f"hello {i}"}, session_id)
            await shared_api.push_event(session_id, event)

        sessions = shared_api.list_sessions()
        assert len(sessions) >= 2

        for session_id in session_ids:
            cleanup_test_session(session_id)

    @pytest.mark.asyncio
    async def test_delete_session(self, shared_api, unique_session_id):
        event = Event("user.message", {"text": "hello"}, unique_session_id)
        await shared_api.push_event(unique_session_id, event)
        await asyncio.sleep(0.3)

        await shared_api.delete_session(unique_session_id)
        retrieved = shared_api.get_session(unique_session_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_repeated_push_event(self, shared_api, main_agent_id):
        session_ids = [f"repeat_test_{i}_{uuid.uuid4().hex[:8]}" for i in range(3)]
        for i, session_id in enumerate(session_ids):
            event = Event("user.message", {"text": f"hello {i}"}, session_id)
            session = await shared_api.push_event(session_id, event)
            assert session is not None

        for session_id in session_ids:
            cleanup_test_session(session_id)


class TestBridgeToolCall:
    """Bridge 工具调用测试"""

    @pytest.mark.asyncio
    async def test_run_shell_tool(self, shared_api, unique_session_id):
        event = Event("user.message", {"text": "run ls command"}, unique_session_id)
        await shared_api.push_event(unique_session_id, event)
        await asyncio.sleep(3)

        state = shared_api.get_state(unique_session_id)
        assert state is not None

        if state.get("tool_results"):
            result = state["tool_results"][0]
            assert result["tool_name"] == "run_shell"

        cleanup_test_session(unique_session_id)


class TestBridgeStreaming:
    """Bridge 流式输出测试"""

    @pytest.mark.asyncio
    async def test_stream_chunks_received(self, shared_api, unique_session_id):
        event = Event("user.message", {"text": "say hello"}, unique_session_id)
        await shared_api.push_event(unique_session_id, event)

        chunks = []
        async for ev in shared_api.stream_events(unique_session_id):
            if ev.type == "stream.chunk":
                chunks.append(ev.payload.get("delta", ""))
            elif ev.type in ("stream.end", "error"):
                break

        assert len(chunks) > 0, "Should receive streaming chunks"
        cleanup_test_session(unique_session_id)

    @pytest.mark.asyncio
    async def test_stream_end_received(self, shared_api, unique_session_id):
        event = Event("user.message", {"text": "hello"}, unique_session_id)
        await shared_api.push_event(unique_session_id, event)

        end_received = False
        async for ev in shared_api.stream_events(unique_session_id):
            if ev.type == "stream.end":
                end_received = True
                break

        assert end_received, "Should receive stream.end event"
        cleanup_test_session(unique_session_id)
