"""Channel Commands Integration Tests

测试飞书、Telegram 等渠道的命令处理功能。
包括：/new, /clear, /session, /session_list
"""

import asyncio
import json
import os
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
        db_file = os.path.join(tmpdir, "sessions.json")
        yield db_file


@pytest.fixture
def mock_api():
    return MockAPI()


class TestChannelCommands:
    """渠道命令测试"""

    @pytest.mark.asyncio
    async def test_new_command_creates_new_session(self, temp_session_db, mock_api):
        """测试 /new 命令创建新会话"""
        from gateway.channels.handlers import handle_channel_command, SESSION_DB_FILE

        original_file = SESSION_DB_FILE
        import gateway.channels.handlers as handlers

        handlers.SESSION_DB_FILE = temp_session_db

        sent_messages = []

        async def mock_send(msg, session_id):
            sent_messages.append({"msg": msg, "session_id": session_id})
            return {"code": 0}

        try:
            result = await handle_channel_command(
                channel_name="feishu",
                sender_id="old_session_id",
                text_content="/new",
                api=mock_api,
                send_func=mock_send,
            )

            assert result[0] is True, "/new should return True"
            assert len(sent_messages) == 1
            assert "已创建新会话" in sent_messages[0]["msg"]
            assert "会话 ID：" in sent_messages[0]["msg"]
        finally:
            handlers.SESSION_DB_FILE = original_file

    @pytest.mark.asyncio
    async def test_clear_command_clears_messages(self, temp_session_db, mock_api):
        """测试 /clear 命令清空消息"""
        from gateway.channels.handlers import handle_channel_command, SESSION_DB_FILE

        original_file = SESSION_DB_FILE
        import gateway.channels.handlers as handlers

        handlers.SESSION_DB_FILE = temp_session_db

        Path(temp_session_db).write_text(
            json.dumps(
                {
                    "test_session": {
                        "session_id": "test_session",
                        "agent_id": "main_agent",
                    }
                }
            )
        )

        session_dir = Path(temp_session_db).parent / "sessions" / "test_session"
        session_dir.mkdir(parents=True)
        messages_file = session_dir / "messages.jsonl"
        messages_file.write_text('{"role":"user","content":"hello"}\n')

        sent_messages = []

        async def mock_send(msg, session_id):
            sent_messages.append({"msg": msg, "session_id": session_id})
            return {"code": 0}

        try:
            result = await handle_channel_command(
                channel_name="feishu",
                sender_id="test_session",
                text_content="/clear",
                api=mock_api,
                send_func=mock_send,
            )

            assert result[0] is True, "/clear should return True"
            assert len(sent_messages) == 1
            assert "已清空" in sent_messages[0]["msg"]
            assert "test_session" in sent_messages[0]["msg"]
        finally:
            handlers.SESSION_DB_FILE = original_file

    @pytest.mark.asyncio
    async def test_session_list_command_lists_sessions(self, temp_session_db, mock_api):
        """测试 /session_list 命令列出所有会话"""
        from gateway.channels.handlers import handle_channel_command, SESSION_DB_FILE

        original_file = SESSION_DB_FILE
        import gateway.channels.handlers as handlers

        handlers.SESSION_DB_FILE = temp_session_db

        Path(temp_session_db).write_text(
            json.dumps(
                {
                    "session_001": {
                        "session_id": "session_001",
                        "agent_id": "main_agent",
                    },
                    "session_002": {
                        "session_id": "session_002",
                        "agent_id": "main_agent",
                    },
                }
            )
        )

        sent_messages = []

        async def mock_send(msg, session_id):
            sent_messages.append({"msg": msg, "session_id": session_id})
            return {"code": 0}

        try:
            result = await handle_channel_command(
                channel_name="feishu",
                sender_id="any_session",
                text_content="/session_list",
                api=mock_api,
                send_func=mock_send,
            )

            assert result[0] is True, "/session_list should return True"
            assert len(sent_messages) == 1
            reply = sent_messages[0]["msg"]
            assert "当前所有会话" in reply
            assert "session_001" in reply
            assert "session_002" in reply
        finally:
            handlers.SESSION_DB_FILE = original_file

    @pytest.mark.asyncio
    async def test_session_command_switches_session(self, temp_session_db, mock_api):
        """测试 /session <id> 命令切换会话"""
        from gateway.channels.handlers import handle_channel_command, SESSION_DB_FILE

        original_file = SESSION_DB_FILE
        import gateway.channels.handlers as handlers

        handlers.SESSION_DB_FILE = temp_session_db

        Path(temp_session_db).write_text(
            json.dumps(
                {
                    "target_session": {
                        "session_id": "target_session",
                        "agent_id": "main_agent",
                    },
                }
            )
        )

        sent_messages = []

        async def mock_send(msg, session_id):
            sent_messages.append({"msg": msg, "session_id": session_id})
            return {"code": 0}

        try:
            result = await handle_channel_command(
                channel_name="feishu",
                sender_id="current_session",
                text_content="/session target_session",
                api=mock_api,
                send_func=mock_send,
            )

            assert result[0] is True, "/session should return True"
            assert len(sent_messages) == 1
            assert "已切换到会话" in sent_messages[0]["msg"]
            assert "target_session" in sent_messages[0]["msg"]
        finally:
            handlers.SESSION_DB_FILE = original_file

    @pytest.mark.asyncio
    async def test_session_command_not_found(self, temp_session_db, mock_api):
        """测试 /session <不存在id> 返回未找到"""
        from gateway.channels.handlers import handle_channel_command, SESSION_DB_FILE

        original_file = SESSION_DB_FILE
        import gateway.channels.handlers as handlers

        handlers.SESSION_DB_FILE = temp_session_db

        Path(temp_session_db).write_text(json.dumps({}))

        sent_messages = []

        async def mock_send(msg, session_id):
            sent_messages.append({"msg": msg, "session_id": session_id})
            return {"code": 0}

        try:
            result = await handle_channel_command(
                channel_name="feishu",
                sender_id="current_session",
                text_content="/session nonexistent",
                api=mock_api,
                send_func=mock_send,
            )

            assert result[0] is True
            assert len(sent_messages) == 1
            assert "未找到会话" in sent_messages[0]["msg"]
        finally:
            handlers.SESSION_DB_FILE = original_file

    @pytest.mark.asyncio
    async def test_non_command_returns_false(self, temp_session_db, mock_api):
        """测试非命令消息返回 False（交给 AI 处理）"""
        from gateway.channels.handlers import handle_channel_command, SESSION_DB_FILE

        original_file = SESSION_DB_FILE
        import gateway.channels.handlers as handlers

        handlers.SESSION_DB_FILE = temp_session_db

        sent_messages = []

        async def mock_send(msg, session_id):
            sent_messages.append({"msg": msg, "session_id": session_id})
            return {"code": 0}

        try:
            result = await handle_channel_command(
                channel_name="feishu",
                sender_id="any_session",
                text_content="你好",
                api=mock_api,
                send_func=mock_send,
            )

            assert result[0] is False, "Non-command should return False"
            assert len(sent_messages) == 0, "Non-command should not send any message"
        finally:
            handlers.SESSION_DB_FILE = original_file

    @pytest.mark.asyncio
    async def test_command_with_extra_spaces(self, temp_session_db, mock_api):
        """测试命令带多余空格"""
        from gateway.channels.handlers import handle_channel_command, SESSION_DB_FILE

        original_file = SESSION_DB_FILE
        import gateway.channels.handlers as handlers

        handlers.SESSION_DB_FILE = temp_session_db

        sent_messages = []

        async def mock_send(msg, session_id):
            sent_messages.append({"msg": msg, "session_id": session_id})
            return {"code": 0}

        try:
            result = await handle_channel_command(
                channel_name="feishu",
                sender_id="any_session",
                text_content="/new   ",
                api=mock_api,
                send_func=mock_send,
            )

            assert result[0] is True, "/new with spaces should still work"
        finally:
            handlers.SESSION_DB_FILE = original_file


class TestChannelMessageWithCommands:
    """测试 handle_channel_message 对命令的处理"""

    @pytest.mark.asyncio
    async def test_message_with_command_is_handled(self, temp_session_db):
        """测试消息是命令时被正确处理"""
        from gateway.channels.handlers import handle_channel_message, SESSION_DB_FILE

        original_file = SESSION_DB_FILE
        import gateway.channels.handlers as handlers

        handlers.SESSION_DB_FILE = temp_session_db

        Path(temp_session_db).write_text(json.dumps({}))

        mock_api = MockAPI()
        sent_messages = []

        async def mock_send(msg, session_id):
            sent_messages.append({"msg": msg, "session_id": session_id})
            return {"code": 0}

        try:
            result = await handle_channel_message(
                channel_name="feishu",
                sender_id="test_session",
                text_content="/new",
                api=mock_api,
                send_func=mock_send,
            )

            assert result[0] is True, "Command message should be handled"
            assert len(sent_messages) == 1
            assert "已创建新会话" in sent_messages[0]["msg"]
        finally:
            handlers.SESSION_DB_FILE = original_file

    @pytest.mark.asyncio
    async def test_regular_message_passed_to_ai(self, temp_session_db):
        """测试普通消息被传递给 AI"""
        from gateway.channels.handlers import handle_channel_message, SESSION_DB_FILE
        from fastmind import Event

        original_file = SESSION_DB_FILE
        import gateway.channels.handlers as handlers

        handlers.SESSION_DB_FILE = temp_session_db

        Path(temp_session_db).write_text(json.dumps({}))

        class MockStreamAPI(MockAPI):
            def __init__(self):
                super().__init__()
                self.stream_events_called = False

            async def stream_events(self, session_id):
                self.stream_events_called = True
                yield Event(type="stream.end", payload={}, session_id=session_id)

        mock_api = MockStreamAPI()
        sent_messages = []

        async def mock_send(msg, session_id):
            sent_messages.append({"msg": msg})
            return {"code": 0}

        try:
            result = await handle_channel_message(
                channel_name="feishu",
                sender_id="test_session",
                text_content="你好",
                api=mock_api,
                send_func=mock_send,
            )

            assert mock_api.stream_events_called, (
                "stream_events should be called for regular message"
            )
        finally:
            handlers.SESSION_DB_FILE = original_file


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
