"""消息存储测试"""

import json
from pathlib import Path

from core.app import save_messages_to_jsonl, load_messages_from_jsonl
from core import config as config_module


def _patch_workspace(monkeypatch, tmp_path):
    ws = tmp_path / "fastclaw_ws"
    monkeypatch.setenv("FASTCLAW_WORKSPACE", str(ws))
    config_module.get_workspace_path.cache_clear()
    sessions_dir = ws / "data" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return ws


class TestMessagesStorage:
    """消息存储测试 — 使用真实的 save/load 函数"""

    def test_save_and_load_with_timestamp(self, tmp_path, monkeypatch):
        _patch_workspace(monkeypatch, tmp_path)
        session_id = "test_timestamp"
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "tool", "tool_call_id": "call_1", "content": "tool result"},
        ]

        save_messages_to_jsonl(session_id, messages)
        loaded = load_messages_from_jsonl(session_id)

        assert len(loaded) == len(messages), "load 必须返回全部消息，不做截断"
        for msg in loaded:
            assert "timestamp" in msg, "timestamp 必须保留"
            assert "role" in msg
            assert "content" in msg

    def test_save_messages_creates_directory(self, tmp_path, monkeypatch):
        ws = _patch_workspace(monkeypatch, tmp_path)
        session_id = "test_session_save"
        messages = [{"role": "user", "content": "Hello"}]
        save_messages_to_jsonl(session_id, messages)

        session_file = ws / "data" / "sessions" / session_id / "messages.jsonl"
        assert session_file.exists()

    def test_save_and_load_messages(self, tmp_path, monkeypatch):
        _patch_workspace(monkeypatch, tmp_path)
        session_id = "test_session_load"
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        save_messages_to_jsonl(session_id, messages)
        loaded = load_messages_from_jsonl(session_id)

        assert len(loaded) == 2
        assert loaded[0]["role"] == "user"
        assert loaded[1]["role"] == "assistant"

    def test_save_multiple_messages_one_per_line(self, tmp_path, monkeypatch):
        _patch_workspace(monkeypatch, tmp_path)
        session_id = "test_multi_line"
        messages = [
            {"role": "user", "content": "Line 1"},
            {"role": "assistant", "content": "Line 2"},
            {"role": "tool", "content": "Line 3"},
        ]

        save_messages_to_jsonl(session_id, messages)
        loaded = load_messages_from_jsonl(session_id)

        assert len(loaded) == 3
        assert loaded[0]["content"] == "Line 1"
        assert loaded[1]["content"] == "Line 2"
        assert loaded[2]["content"] == "Line 3"


class TestLoadMessagesEdgeCases:
    """加载消息边界情况 — 使用真实的 load 函数"""

    def test_load_from_empty_file(self, tmp_path, monkeypatch):
        ws = _patch_workspace(monkeypatch, tmp_path)
        session_id = "test_empty"
        session_dir = ws / "data" / "sessions" / session_id
        session_dir.mkdir(parents=True)
        (session_dir / "messages.jsonl").write_text("")

        loaded = load_messages_from_jsonl(session_id)
        assert loaded == []

    def test_load_with_invalid_json(self, tmp_path, monkeypatch):
        ws = _patch_workspace(monkeypatch, tmp_path)
        session_id = "test_invalid"
        session_dir = ws / "data" / "sessions" / session_id
        session_dir.mkdir(parents=True)
        (session_dir / "messages.jsonl").write_text("invalid json\n")

        loaded = load_messages_from_jsonl(session_id)
        assert loaded == []

    def test_load_with_mixed_valid_invalid(self, tmp_path, monkeypatch):
        ws = _patch_workspace(monkeypatch, tmp_path)
        session_id = "test_mixed"
        session_dir = ws / "data" / "sessions" / session_id
        session_dir.mkdir(parents=True)
        (session_dir / "messages.jsonl").write_text(
            '{"role": "user", "content": "valid"}\ninvalid\n{"role": "assistant", "content": "also valid"}'
        )

        loaded = load_messages_from_jsonl(session_id)
        assert len(loaded) == 2
        assert loaded[0]["role"] == "user"
        assert loaded[1]["role"] == "assistant"

    def test_load_with_tool_messages(self, tmp_path, monkeypatch):
        _patch_workspace(monkeypatch, tmp_path)
        session_id = "test_tool"
        messages = [
            {"role": "user", "content": "Run command"},
            {"role": "assistant", "content": "Running..."},
            {"role": "tool", "tool_call_id": "call_1", "content": "[run_shell]: output"},
        ]
        save_messages_to_jsonl(session_id, messages)
        loaded = load_messages_from_jsonl(session_id)

        assert len(loaded) == 3
        assert loaded[2]["role"] == "tool"
        assert "tool_call_id" in loaded[2]


class TestMessagesContent:
    """消息内容测试"""

    def test_messages_have_required_fields(self):
        message = {"role": "user", "content": "Hello"}
        assert "role" in message
        assert "content" in message
        assert message["role"] in ["user", "assistant", "system", "tool"]

    def test_tool_message_has_tool_call_id(self):
        message = {"role": "tool", "tool_call_id": "call_abc123", "content": "[run_shell]: result"}
        assert message["role"] == "tool"
        assert "tool_call_id" in message

    def test_assistant_message_with_tool_calls(self):
        message = {
            "role": "assistant",
            "content": "I'll run that command",
            "tool_calls": [{"id": "call_1", "function": {"name": "run_shell", "arguments": "{}"}}],
        }
        assert message["role"] == "assistant"
        assert "tool_calls" in message

    def test_message_json_roundtrip_chinese(self):
        message = {"role": "user", "content": "你好世界"}
        encoded = json.dumps(message, ensure_ascii=False)
        decoded = json.loads(encoded)
        assert decoded["content"] == "你好世界"

    def test_message_json_roundtrip_emoji(self):
        message = {"role": "user", "content": "Hello 👋"}
        encoded = json.dumps(message, ensure_ascii=False)
        decoded = json.loads(encoded)
        assert "👋" in decoded["content"]


class TestMessagesConversation:
    """对话消息测试"""

    def test_conversation_messages_sequence(self):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "I'm doing well!"},
        ]
        roles = [m["role"] for m in messages]
        assert roles == ["system", "user", "assistant", "user", "assistant"]

    def test_tool_call_conversation(self):
        messages = [
            {"role": "user", "content": "List files"},
            {
                "role": "assistant",
                "content": "I'll list the files...",
                "tool_calls": [{"id": "call_1", "function": {"name": "run_shell", "arguments": '{"command": "ls"}'}}],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "[run_shell]: file1.txt\nfile2.txt"},
            {"role": "assistant", "content": "I found file1.txt and file2.txt."},
        ]
        assert len(messages) == 4
        assert messages[1]["tool_calls"][0]["function"]["name"] == "run_shell"
        assert messages[2]["role"] == "tool"

    def test_multi_turn_conversation(self):
        messages = [
            {"role": "user", "content": "Turn 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Turn 2"},
            {"role": "assistant", "content": "Response 2"},
            {"role": "user", "content": "Turn 3"},
            {"role": "assistant", "content": "Response 3"},
        ]
        for i in range(len(messages)):
            if i % 2 == 0:
                assert messages[i]["role"] == "user"
            else:
                assert messages[i]["role"] == "assistant"


class TestMessageStorageEdgeCases:
    """消息存储边界情况测试"""

    def test_empty_content(self):
        message = {"role": "user", "content": ""}
        encoded = json.dumps(message)
        decoded = json.loads(encoded)
        assert decoded["content"] == ""

    def test_very_long_content(self):
        long_text = "x" * 100000
        message = {"role": "user", "content": long_text}
        encoded = json.dumps(message)
        decoded = json.loads(encoded)
        assert len(decoded["content"]) == 100000

    def test_special_characters_in_content(self):
        message = {"role": "user", "content": 'Line1\nLine2\tTabbed"Quoted"'}
        encoded = json.dumps(message)
        decoded = json.loads(encoded)
        assert "\n" in decoded["content"]
        assert "\t" in decoded["content"]

    def test_unicode_in_content(self):
        message = {"role": "user", "content": "日本語中文한국어"}
        encoded = json.dumps(message, ensure_ascii=False)
        decoded = json.loads(encoded)
        assert decoded["content"] == "日本語中文한국어"
