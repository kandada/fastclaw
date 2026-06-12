"""Channel Commands Integration Tests

测试飞书、Telegram 等渠道的命令处理功能。
包括：/new, /clear, /session, /session_list
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


class MockAPI:
    """Mock FastMindAPI for command testing"""

    def __init__(self):
        self.pushed_events = []

    async def push_event(self, session_id, event):
        self.pushed_events.append((session_id, event))
        return {"status": "ok"}

    async def start(self):
        pass

    async def stop(self):
        pass


@pytest.fixture
def temp_session_db():
    """临时 session 数据库"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "sessions.json"
        yield db_file


@pytest.fixture
def mock_api():
    return MockAPI()


@pytest.fixture
def patched_session_db(temp_session_db, monkeypatch):
    """patch get_sessions_dir 到临时路径，测试后自动恢复"""
    import fastclaw.core.config as config_mod
    temp_sessions_dir = temp_session_db.parent
    monkeypatch.setattr(config_mod, "get_sessions_dir", lambda: temp_sessions_dir)
    config_mod._session_store = None
    yield temp_session_db
    config_mod._session_store = None


@pytest.fixture
def mock_send():
    sent_messages = []

    async def _send(msg, session_id):
        sent_messages.append({"msg": msg, "session_id": session_id})
        return {"code": 0}

    return _send, sent_messages


class TestChannelCommands:
    """渠道命令测试"""

    @pytest.mark.asyncio
    async def test_new_command_creates_new_session(self, patched_session_db, mock_api, mock_send):
        from gateway.channels.handlers import handle_channel_command
        send_func, sent = mock_send

        result = await handle_channel_command(
            channel_name="feishu",
            sender_id="old_session_id",
            text_content="/new",
            api=mock_api,
            send_func=send_func,
        )

        assert result[0] is True, "/new should return True"
        assert len(sent) == 1
        assert "New session created" in sent[0]["msg"]
        assert "ID:" in sent[0]["msg"]

    @pytest.mark.asyncio
    async def test_clear_command_clears_messages(self, patched_session_db, mock_api, mock_send):
        from gateway.channels.handlers import handle_channel_command
        send_func, sent = mock_send

        patched_session_db.write_text(json.dumps({
            "test_session": {"session_id": "test_session", "agent_id": "main_agent"}
        }))

        session_dir = patched_session_db.parent / "test_session"
        session_dir.mkdir(parents=True)
        (session_dir / "messages.jsonl").write_text('{"role":"user","content":"hello"}\n')

        result = await handle_channel_command(
            channel_name="feishu",
            sender_id="test_session",
            text_content="/clear",
            api=mock_api,
            send_func=send_func,
        )

        assert result[0] is True, "/clear should return True"
        assert len(sent) == 1
        assert "Cleared chat history" in sent[0]["msg"]
        assert "test_session" in sent[0]["msg"]

    @pytest.mark.asyncio
    async def test_session_list_command_lists_sessions(self, patched_session_db, mock_api, mock_send):
        from gateway.channels.handlers import handle_channel_command
        send_func, sent = mock_send

        patched_session_db.write_text(json.dumps({
            "session_001": {"session_id": "session_001", "agent_id": "main_agent"},
            "session_002": {"session_id": "session_002", "agent_id": "main_agent"},
        }))

        result = await handle_channel_command(
            channel_name="feishu",
            sender_id="any_session",
            text_content="/session_list",
            api=mock_api,
            send_func=send_func,
        )

        assert result[0] is True, "/session_list should return True"
        assert len(sent) == 1
        reply = sent[0]["msg"]
        assert "All sessions" in reply
        assert "session_001" in reply
        assert "session_002" in reply

    @pytest.mark.asyncio
    async def test_session_command_switches_session(self, patched_session_db, mock_api, mock_send):
        from gateway.channels.handlers import handle_channel_command
        send_func, sent = mock_send

        patched_session_db.write_text(json.dumps({
            "target_session": {"session_id": "target_session", "agent_id": "main_agent"}
        }))

        result = await handle_channel_command(
            channel_name="feishu",
            sender_id="current_session",
            text_content="/session target_session",
            api=mock_api,
            send_func=send_func,
        )

        assert result[0] is True, "/session should return True"
        assert len(sent) == 1
        assert "Switched to session" in sent[0]["msg"]
        assert "target_session" in sent[0]["msg"]

    @pytest.mark.asyncio
    async def test_session_command_not_found(self, patched_session_db, mock_api, mock_send):
        from gateway.channels.handlers import handle_channel_command
        send_func, sent = mock_send

        patched_session_db.write_text(json.dumps({}))

        result = await handle_channel_command(
            channel_name="feishu",
            sender_id="current_session",
            text_content="/session nonexistent",
            api=mock_api,
            send_func=send_func,
        )

        assert result[0] is True
        assert len(sent) == 1
        assert "Session not found" in sent[0]["msg"]

    @pytest.mark.asyncio
    async def test_non_command_returns_false(self, patched_session_db, mock_api, mock_send):
        from gateway.channels.handlers import handle_channel_command
        send_func, sent = mock_send

        result = await handle_channel_command(
            channel_name="feishu",
            sender_id="any_session",
            text_content="你好",
            api=mock_api,
            send_func=send_func,
        )

        assert result[0] is False, "Non-command should return False"
        assert len(sent) == 0, "Non-command should not send any message"

    @pytest.mark.asyncio
    async def test_command_with_extra_spaces(self, patched_session_db, mock_api, mock_send):
        from gateway.channels.handlers import handle_channel_command
        send_func, sent = mock_send

        result = await handle_channel_command(
            channel_name="feishu",
            sender_id="any_session",
            text_content="/new   ",
            api=mock_api,
            send_func=send_func,
        )

        assert result[0] is True, "/new with spaces should still work"


class TestChannelMessageWithCommands:
    """测试 handle_channel_message 对命令的处理"""

    @pytest.mark.asyncio
    async def test_message_with_command_is_handled(self, patched_session_db, mock_send):
        from gateway.channels.handlers import handle_channel_message

        mock_api = MockAPI()
        send_func, sent = mock_send

        patched_session_db.write_text(json.dumps({}))

        result = await handle_channel_message(
            channel_name="feishu",
            sender_id="test_session",
            text_content="/new",
            api=mock_api,
            send_func=send_func,
        )

        assert result[0] is True, "Command message should be handled"
        assert len(sent) == 1
        assert "New session created" in sent[0]["msg"]

    @pytest.mark.asyncio
    async def test_regular_message_passed_to_ai(self, patched_session_db, mock_send):
        from gateway.channels.handlers import handle_channel_message
        from fastmind import Event

        patched_session_db.write_text(json.dumps({}))

        class MockStreamAPI(MockAPI):
            def __init__(self):
                super().__init__()
                self.stream_events_called = False

            async def stream_events(self, session_id):
                self.stream_events_called = True
                yield Event(type="stream.end", payload={}, session_id=session_id)

        mock_api = MockStreamAPI()
        send_func, sent = mock_send

        await handle_channel_message(
            channel_name="feishu",
            sender_id="test_session",
            text_content="你好",
            api=mock_api,
            send_func=send_func,
        )

        assert mock_api.stream_events_called, "stream_events should be called for regular message"
