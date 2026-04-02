"""Channel Message Handler 测试"""

import json
import pytest
import pytest_asyncio
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastmind import Event


class MockStreamEventsAPI:
    """Mock FastMindAPI that correctly simulates stream_events behavior"""

    def __init__(self, include_thinking=False, include_tools=False):
        self.sessions = {}
        self._event_queues = {}
        self.include_thinking = include_thinking
        self.include_tools = include_tools

    async def push_event(self, session_id, event):
        if session_id not in self.sessions:
            self.sessions[session_id] = {"messages": []}
            self._event_queues[session_id] = asyncio.Queue()

        msg = event.payload.get("text", "")
        self.sessions[session_id]["messages"].append({"role": "user", "content": msg})
        return self.sessions[session_id]

    def get_state(self, session_id):
        return self.sessions.get(session_id)

    async def stream_events(self, session_id):
        """Simulate AI processing and streaming response with thinking and tools"""
        if self.include_thinking:
            yield Event(
                type="stream.thinking",
                payload={"delta": "正在思考..."},
                session_id=session_id,
            )
            await asyncio.sleep(0.02)

        if self.include_tools:
            yield Event(
                type="stream.fragment",
                payload={
                    "has_tool_calls": True,
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": '{"city":"北京"}',
                            },
                        }
                    ],
                },
                session_id=session_id,
            )
            await asyncio.sleep(0.02)

        for i, chunk in enumerate(["这", "是", "测", "试", "响", "应"]):
            yield Event(
                type="stream.chunk",
                payload={"delta": chunk},
                session_id=session_id,
            )
            await asyncio.sleep(0.01)

        yield Event(type="stream.end", payload={}, session_id=session_id)

    async def start(self):
        pass

    async def stop(self):
        pass


@pytest_asyncio.fixture
async def mock_api():
    return MockStreamEventsAPI()


@pytest_asyncio.fixture
async def feishu_adapter(mock_api):
    from gateway.channels.feishu import FeishuAdapter
    from gateway.channels import handlers

    adapter = FeishuAdapter()
    adapter.tenant_token = "mock_token"

    sent_messages = []

    async def mock_send(msg, open_id=None, chat_id=None):
        sent_messages.append({"msg": msg, "open_id": open_id})
        return {"code": 0}

    adapter.send_message = mock_send

    return adapter, mock_api, sent_messages


class TestChannelMessageHandler:
    """测试通用 channel message handler"""

    @pytest.mark.asyncio
    async def test_handler_uses_stream_events_not_get_state(self, feishu_adapter):
        """验证 handler 使用 stream_events 而不是 get_state"""
        adapter, mock_api, sent_messages = feishu_adapter

        original_get_state = mock_api.get_state
        get_state_called = []

        def tracked_get_state(session_id):
            get_state_called.append(session_id)
            return original_get_state(session_id)

        mock_api.get_state = tracked_get_state

        mock_stream_events = []
        original_stream = mock_api.stream_events

        async def tracked_stream(session_id):
            async for ev in original_stream(session_id):
                mock_stream_events.append(ev)
                yield ev

        mock_api.stream_events = tracked_stream

        import gateway.router

        gateway.router._websocket_api = mock_api

        class MockSender:
            class SenderId:
                open_id = "ou_test_stream"

            sender_id = SenderId()

        class MockEvent:
            message = type(
                "obj",
                (object,),
                {
                    "message_type": "text",
                    "content": '{"text":"测试消息"}',
                },
            )()
            sender = MockSender()

        class MockData:
            event = MockEvent()

        await adapter._handle_feishu_message(MockData())

        await asyncio.sleep(0.5)

        assert len(mock_stream_events) > 0, "stream_events should be called"

        stream_types = [ev.type for ev in mock_stream_events]
        assert "stream.chunk" in stream_types or "stream.end" in stream_types

        assert len(sent_messages) > 0, "Should send message"
        assert sent_messages[0]["msg"] != "测试消息", (
            "Reply should NOT be echo of input"
        )

    @pytest.mark.asyncio
    async def test_handler_accumulates_chunks(self, feishu_adapter):
        """验证 handler 正确累积 stream.chunk"""
        adapter, mock_api, sent_messages = feishu_adapter

        import gateway.router

        gateway.router._websocket_api = mock_api

        class MockSender:
            class SenderId:
                open_id = "ou_test_chunks"

            sender_id = SenderId()

        class MockEvent:
            message = type(
                "obj",
                (object,),
                {
                    "message_type": "text",
                    "content": '{"text":"你好"}',
                },
            )()
            sender = MockSender()

        class MockData:
            event = MockEvent()

        await adapter._handle_feishu_message(MockData())

        await asyncio.sleep(0.5)

        if sent_messages:
            reply = sent_messages[0]["msg"]
            assert "测试" in reply or "响应" in reply, (
                f"Reply should be AI response, got: {reply}"
            )


class TestFeishuMessageFlow:
    """测试飞书消息处理流程"""

    @pytest.mark.asyncio
    async def test_text_message_extraction(self, feishu_adapter):
        """测试文本消息正确提取"""
        adapter, mock_api, sent_messages = feishu_adapter

        import gateway.router

        gateway.router._websocket_api = mock_api

        class MockSender:
            class SenderId:
                open_id = "ou_123"

            sender_id = SenderId()

        class MockEvent:
            message = type(
                "obj",
                (object,),
                {
                    "message_type": "text",
                    "content": '{"text":"飞书消息"}',
                },
            )()
            sender = MockSender()

        class MockData:
            event = MockEvent()

        await adapter._handle_feishu_message(MockData())
        await asyncio.sleep(0.3)

    @pytest.mark.asyncio
    async def test_session_is_sender_open_id(self, feishu_adapter):
        """验证 session_id 使用 sender 的 open_id"""
        adapter, mock_api, sent_messages = feishu_adapter

        import gateway.router

        gateway.router._websocket_api = mock_api

        sender_open_id = "ou_sender_abc123"

        class MockSender:
            class SenderId:
                open_id = sender_open_id

            sender_id = SenderId()

        class MockEvent:
            message = type(
                "obj",
                (object,),
                {
                    "message_type": "text",
                    "content": '{"text":"test"}',
                },
            )()
            sender = MockSender()

        class MockData:
            event = MockEvent()

        await adapter._handle_feishu_message(MockData())
        await asyncio.sleep(0.3)


class TestChannelHandlerSharedLogic:
    """测试 channel handler 共享逻辑可以被不同 channel 使用"""

    @pytest.mark.asyncio
    async def test_handler_is_importable(self):
        """验证 handlers 模块可以正常导入"""
        from gateway.channels import handlers

        assert hasattr(handlers, "handle_channel_message")
        assert asyncio.iscoroutinefunction(handlers.handle_channel_message)

    @pytest.mark.asyncio
    async def test_handler_function_signature(self):
        """验证 handler 函数签名正确"""
        from gateway.channels.handlers import handle_channel_message
        import inspect

        sig = inspect.signature(handle_channel_message)
        params = list(sig.parameters.keys())
        assert "channel_name" in params
        assert "sender_id" in params
        assert "text_content" in params
        assert "api" in params
        assert "send_func" in params
        assert "include_thinking" in params
        assert "include_tools" in params


class TestThinkingAndToolInfo:
    """测试思考内容和工具信息的收集与返回"""

    @pytest.mark.asyncio
    async def test_thinking_content_included_in_response(self):
        """验证思考内容被包含在回复中"""
        from gateway.channels.handlers import handle_channel_message

        mock_api = MockStreamEventsAPI(include_thinking=True, include_tools=False)
        sent_messages = []

        async def mock_send(msg, session_id):
            sent_messages.append({"msg": msg, "session_id": session_id})
            return {"code": 0}

        import gateway.router

        gateway.router._websocket_api = mock_api

        await handle_channel_message(
            channel_name="test",
            sender_id="ou_test_thinking",
            text_content="你好",
            api=mock_api,
            send_func=mock_send,
            include_thinking=True,
            include_tools=False,
        )

        await asyncio.sleep(0.3)

        assert len(sent_messages) > 0, "Should send message"
        reply = sent_messages[0]["msg"]
        assert "测试响应" in reply or "响应" in reply, (
            f"Reply should contain response text, got: {reply}"
        )
        assert "[思考...]" in reply, (
            f"Reply should contain [思考...] label, got: {reply}"
        )

    @pytest.mark.asyncio
    async def test_tool_calls_included_in_response(self):
        """验证工具调用信息被包含在回复中"""
        from gateway.channels.handlers import handle_channel_message

        mock_api = MockStreamEventsAPI(include_thinking=False, include_tools=True)
        sent_messages = []

        async def mock_send(msg, session_id):
            sent_messages.append({"msg": msg, "session_id": session_id})
            return {"code": 0}

        import gateway.router

        gateway.router._websocket_api = mock_api

        await handle_channel_message(
            channel_name="test",
            sender_id="ou_test_tools",
            text_content="查一下天气",
            api=mock_api,
            send_func=mock_send,
            include_thinking=False,
            include_tools=True,
        )

        await asyncio.sleep(0.3)

        assert len(sent_messages) > 0, "Should send message"
        reply = sent_messages[0]["msg"]
        assert "测试响应" in reply or "响应" in reply, (
            f"Reply should contain response text, got: {reply}"
        )
        assert "[工具执行...]" in reply or "get_weather" in reply, (
            f"Reply should contain [工具执行...] label, got: {reply}"
        )

    @pytest.mark.asyncio
    async def test_thinking_and_tools_both_included(self):
        """验证思考内容和工具信息同时被包含在回复中"""
        from gateway.channels.handlers import handle_channel_message

        mock_api = MockStreamEventsAPI(include_thinking=True, include_tools=True)
        sent_messages = []

        async def mock_send(msg, session_id):
            sent_messages.append({"msg": msg, "session_id": session_id})
            return {"code": 0}

        import gateway.router

        gateway.router._websocket_api = mock_api

        await handle_channel_message(
            channel_name="test",
            sender_id="ou_test_both",
            text_content="你好",
            api=mock_api,
            send_func=mock_send,
            include_thinking=True,
            include_tools=True,
        )

        await asyncio.sleep(0.3)

        assert len(sent_messages) > 0, "Should send message"
        reply = sent_messages[0]["msg"]
        assert "[思考...]" in reply, f"Reply should contain [思考...], got: {reply}"
        assert "[工具执行...]" in reply or "get_weather" in reply, (
            f"Reply should contain [工具执行...], got: {reply}"
        )

    @pytest.mark.asyncio
    async def test_thinking_excluded_when_disabled(self):
        """验证 include_thinking=False 时不包含思考内容"""
        from gateway.channels.handlers import handle_channel_message

        mock_api = MockStreamEventsAPI(include_thinking=True, include_tools=False)
        sent_messages = []

        async def mock_send(msg, session_id):
            sent_messages.append({"msg": msg, "session_id": session_id})
            return {"code": 0}

        import gateway.router

        gateway.router._websocket_api = mock_api

        await handle_channel_message(
            channel_name="test",
            sender_id="ou_test_no_thinking",
            text_content="你好",
            api=mock_api,
            send_func=mock_send,
            include_thinking=False,
            include_tools=False,
        )

        await asyncio.sleep(0.3)

        assert len(sent_messages) > 0, "Should send message"
        reply = sent_messages[0]["msg"]
        assert "[思考]" not in reply, (
            f"Reply should NOT contain [思考] when disabled, got: {reply}"
        )


class TestChannelCommands:
    """测试渠道命令处理"""

    @pytest.mark.asyncio
    async def test_new_command_creates_session(self):
        """测试 /new 命令创建新会话"""
        from gateway.channels.handlers import handle_channel_command
        import tempfile
        import os

        mock_api = MockStreamEventsAPI()
        sent_messages = []

        async def mock_send(msg, session_id):
            sent_messages.append({"msg": msg, "session_id": session_id})
            return {"code": 0}

        import gateway.router

        gateway.router._websocket_api = mock_api

        with tempfile.TemporaryDirectory() as tmpdir:
            original_db = "workspace/data/sessions/sessions.json"
            temp_db = os.path.join(tmpdir, "sessions.json")

            import gateway.channels.handlers as h

            original_file = h.SESSION_DB_FILE
            h.SESSION_DB_FILE = temp_db

            try:
                await handle_channel_command(
                    channel_name="test",
                    sender_id="ou_old_session",
                    text_content="/new",
                    api=mock_api,
                    send_func=mock_send,
                )

                assert len(sent_messages) > 0, "Should send reply"
                reply = sent_messages[0]["msg"]
                assert "已创建新会话" in reply, (
                    f"Should confirm new session, got: {reply}"
                )
                assert "会话 ID：" in reply, f"Should contain session_id, got: {reply}"
            finally:
                h.SESSION_DB_FILE = original_file

    @pytest.mark.asyncio
    async def test_session_list_command(self):
        """测试 /session_list 命令"""
        from gateway.channels.handlers import handle_channel_command
        import tempfile
        import os

        mock_api = MockStreamEventsAPI()
        sent_messages = []

        async def mock_send(msg, session_id):
            sent_messages.append({"msg": msg, "session_id": session_id})
            return {"code": 0}

        import gateway.router

        gateway.router._websocket_api = mock_api

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_db = os.path.join(tmpdir, "sessions.json")

            import gateway.channels.handlers as h

            original_file = h.SESSION_DB_FILE
            h.SESSION_DB_FILE = temp_db

            json.dump(
                {
                    "test_session_1": {
                        "session_id": "test_session_1",
                        "agent_id": "main_agent",
                    }
                },
                open(temp_db, "w"),
            )

            try:
                await handle_channel_command(
                    channel_name="test",
                    sender_id="test_session_1",
                    text_content="/session_list",
                    api=mock_api,
                    send_func=mock_send,
                )

                assert len(sent_messages) > 0, "Should send reply"
                reply = sent_messages[0]["msg"]
                assert "当前所有会话" in reply, f"Should list sessions, got: {reply}"
                assert "test_session_1" in reply, (
                    f"Should contain session id, got: {reply}"
                )
            finally:
                h.SESSION_DB_FILE = original_file

    @pytest.mark.asyncio
    async def test_clear_command(self):
        """测试 /clear 命令"""
        from gateway.channels.handlers import handle_channel_command
        import tempfile
        import os
        from pathlib import Path

        mock_api = MockStreamEventsAPI()
        sent_messages = []

        async def mock_send(msg, session_id):
            sent_messages.append({"msg": msg, "session_id": session_id})
            return {"code": 0}

        import gateway.router

        gateway.router._websocket_api = mock_api

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_db = os.path.join(tmpdir, "sessions.json")
            temp_session_dir = Path(tmpdir) / "sessions" / "test_clear_session"
            temp_session_dir.mkdir(parents=True)
            (temp_session_dir / "messages.jsonl").write_text("test data")

            import gateway.channels.handlers as h

            original_file = h.SESSION_DB_FILE
            h.SESSION_DB_FILE = temp_db

            json.dump(
                {
                    "test_clear_session": {
                        "session_id": "test_clear_session",
                        "agent_id": "main_agent",
                    }
                },
                open(temp_db, "w"),
            )

            try:
                await handle_channel_command(
                    channel_name="test",
                    sender_id="test_clear_session",
                    text_content="/clear",
                    api=mock_api,
                    send_func=mock_send,
                )

                assert len(sent_messages) > 0, "Should send reply"
                reply = sent_messages[0]["msg"]
                assert "已清空" in reply, f"Should confirm clear, got: {reply}"

                assert h.SESSION_DB_FILE == temp_db
            finally:
                h.SESSION_DB_FILE = original_file

    @pytest.mark.asyncio
    async def test_non_command_passed_to_ai(self):
        """测试非命令消息正常传递给 AI"""
        from gateway.channels.handlers import handle_channel_command

        mock_api = MockStreamEventsAPI()
        sent_messages = []

        async def mock_send(msg, session_id):
            sent_messages.append({"msg": msg, "session_id": session_id})
            return {"code": 0}

        import gateway.router

        gateway.router._websocket_api = mock_api

        result = await handle_channel_command(
            channel_name="test",
            sender_id="ou_test",
            text_content="你好",
            api=mock_api,
            send_func=mock_send,
        )

        assert result[0] is False, "Non-command should return False"
