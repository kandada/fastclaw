# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""Stop/Cancel 功能测试"""

import pytest
import asyncio

pytestmark = pytest.mark.slow


class TestStopSession:
    """停止会话测试"""

    @pytest.mark.asyncio
    async def test_stop_while_running(self, shared_api, unique_session_id):
        """测试停止正在运行的会话"""
        from fastmind import Event
        from tests.conftest import cleanup_test_session

        await shared_api.push_event(
            unique_session_id,
            Event("user.message", {"text": "say hi"}, unique_session_id),
        )
        await asyncio.sleep(0.3)

        session = shared_api.get_session(unique_session_id)
        assert session is not None

        await session.stop()
        assert session.session_state == "stopped"

        with pytest.raises(RuntimeError, match="is stopped"):
            async for _ in shared_api.stream_events(unique_session_id):
                pass

        cleanup_test_session(unique_session_id)

    @pytest.mark.asyncio
    async def test_stop_idle_session(self, shared_api, unique_session_id):
        """测试停止已空闲的会话"""
        from fastmind import Event
        from tests.conftest import cleanup_test_session

        session = await shared_api.push_event(
            unique_session_id,
            Event("user.message", {"text": "hi"}, unique_session_id),
        )
        await asyncio.sleep(1)

        events = []
        async for ev in shared_api.stream_events(unique_session_id):
            events.append(ev)
            if ev.type in ("stream.end", "error"):
                break

        await session.stop()
        assert session.session_state == "stopped"

        cleanup_test_session(unique_session_id)

    @pytest.mark.asyncio
    async def test_session_reusable_after_stop(self, shared_api, unique_session_id):
        """测试停止后会话可复用"""
        from fastmind import Event
        from tests.conftest import cleanup_test_session

        await shared_api.push_event(
            unique_session_id,
            Event("user.message", {"text": "count to 3"}, unique_session_id),
        )
        await asyncio.sleep(0.3)

        session = shared_api.get_session(unique_session_id)
        await session.stop()
        assert session.session_state == "stopped"

        session2 = await shared_api.push_event(
            unique_session_id,
            Event("user.message", {"text": "say hello"}, unique_session_id),
        )
        assert session2 is not None
        assert session2.session_id == unique_session_id

        await asyncio.sleep(0.5)
        events2 = []
        async for ev in shared_api.stream_events(unique_session_id):
            events2.append(ev)
            if ev.type in ("stream.end", "error"):
                break
        assert len(events2) > 0

        cleanup_test_session(unique_session_id)


class TestStopHTTPEndpoint:
    """HTTP Stop 端点测试"""

    @pytest.mark.asyncio
    async def test_stop_http_nonexistent(self, shared_api, unique_session_id):
        """HTTP 404: 停止不存在的会话"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer
        from gateway.router import set_websocket_api

        set_websocket_api(shared_api)
        server = GatewayServer()

        with TestClient(server.app) as client:
            resp = client.post("/api/chat/stop/nonexistent")
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_stop_http_no_api(self, unique_session_id):
        """HTTP 500: API 未初始化"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer
        from gateway.router import set_websocket_api

        set_websocket_api(None)
        server = GatewayServer()

        with TestClient(server.app) as client:
            resp = client.post(f"/api/chat/stop/{unique_session_id}")
            assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_stop_http_while_running(self, shared_api, unique_session_id):
        """HTTP 200: 停止正在运行的会话"""
        from fastmind import Event
        from gateway.router import set_websocket_api, chat_stop as _chat_stop
        from tests.conftest import cleanup_test_session

        set_websocket_api(shared_api)

        await shared_api.push_event(
            unique_session_id,
            Event("user.message", {"text": "hello"}, unique_session_id),
        )
        await asyncio.sleep(0.3)

        result = await _chat_stop(unique_session_id)
        assert result["status"] == "stopped"
        assert result["session_id"] == unique_session_id

        cleanup_test_session(unique_session_id)


class TestStopSSE:
    """Stop 后 SSE 行为测试"""

    @pytest.mark.asyncio
    async def test_sse_returns_session_stopped_after_stop(self, shared_api, unique_session_id):
        """停止后 SSE 应返回 session_stopped 事件而不是无限重连"""
        from fastapi.testclient import TestClient
        from fastmind import Event
        from gateway.server import GatewayServer
        from gateway.router import set_websocket_api
        from tests.conftest import cleanup_test_session

        set_websocket_api(shared_api)
        server = GatewayServer()

        await shared_api.push_event(
            unique_session_id,
            Event("user.message", {"text": "hi"}, unique_session_id),
        )
        await asyncio.sleep(0.3)

        session = shared_api.get_session(unique_session_id)
        await session.stop()

        with TestClient(server.app) as client:
            with client.stream("GET", f"/api/chat/stream/{unique_session_id}") as resp:
                assert resp.status_code == 200
                events = []
                for line in resp.iter_lines():
                    if line.startswith("event: "):
                        events.append(line[7:])
                    if "session_stopped" in events:
                        break

                assert "session_stopped" in events

        cleanup_test_session(unique_session_id)


