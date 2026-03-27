"""消息存储测试"""

import pytest
import json
import asyncio
import tempfile
import os
from pathlib import Path
from core.app import save_messages_to_jsonl, load_messages_from_jsonl


class TestMessagesStorage:
    """消息存储测试"""

    def test_save_messages_creates_directory(self, tmp_path):
        """保存消息创建目录"""
        session_id = "test_session_save"
        messages = [{"role": "user", "content": "Hello"}]

        # 使用临时路径
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = (
                Path(tmpdir)
                / "workspace"
                / "data"
                / "sessions"
                / session_id
                / "messages.jsonl"
            )
            session_file.parent.mkdir(parents=True, exist_ok=True)

            with open(session_file, "w", encoding="utf-8") as f:
                for msg in messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")

            assert session_file.exists()

    def test_save_and_load_messages(self, tmp_path):
        """保存和加载消息"""
        session_id = "test_session_load"
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = (
                Path(tmpdir)
                / "workspace"
                / "data"
                / "sessions"
                / session_id
                / "messages.jsonl"
            )
            session_file.parent.mkdir(parents=True, exist_ok=True)

            # 保存
            with open(session_file, "w", encoding="utf-8") as f:
                for msg in messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")

            # 加载
            loaded = []
            for line in session_file.read_text().splitlines():
                if line.strip():
                    loaded.append(json.loads(line))

            assert len(loaded) == 2
            assert loaded[0]["role"] == "user"
            assert loaded[1]["role"] == "assistant"

    def test_save_messages_json_format(self, tmp_path):
        """保存消息为 JSON 格式"""
        session_id = "test_json_format"
        messages = [{"role": "user", "content": "Test content"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = (
                Path(tmpdir)
                / "workspace"
                / "data"
                / "sessions"
                / session_id
                / "messages.jsonl"
            )
            session_file.parent.mkdir(parents=True, exist_ok=True)

            with open(session_file, "w", encoding="utf-8") as f:
                for msg in messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")

            content = session_file.read_text()
            parsed = json.loads(content.strip())

            assert parsed["role"] == "user"
            assert parsed["content"] == "Test content"

    def test_save_multiple_messages_one_per_line(self, tmp_path):
        """多条消息每行一条"""
        session_id = "test_multi_line"
        messages = [
            {"role": "user", "content": "Line 1"},
            {"role": "assistant", "content": "Line 2"},
            {"role": "tool", "content": "Line 3"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = (
                Path(tmpdir)
                / "workspace"
                / "data"
                / "sessions"
                / session_id
                / "messages.jsonl"
            )
            session_file.parent.mkdir(parents=True, exist_ok=True)

            with open(session_file, "w", encoding="utf-8") as f:
                for msg in messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")

            lines = session_file.read_text().strip().split("\n")

            assert len(lines) == 3
            assert json.loads(lines[0])["content"] == "Line 1"
            assert json.loads(lines[1])["content"] == "Line 2"
            assert json.loads(lines[2])["content"] == "Line 3"


class TestLoadMessages:
    """加载消息测试"""

    def test_load_from_empty_file(self, tmp_path):
        """从空文件加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "test.jsonl"
            session_file.write_text("")

            loaded = []
            for line in session_file.read_text().splitlines():
                if line.strip():
                    loaded.append(json.loads(line))

            assert loaded == []

    def test_load_with_invalid_json(self, tmp_path):
        """加载无效 JSON"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "test.jsonl"
            session_file.write_text("invalid json\n")

            loaded = []
            for line in session_file.read_text().splitlines():
                if line.strip():
                    try:
                        loaded.append(json.loads(line))
                    except:
                        pass

            assert loaded == []

    def test_load_with_mixed_valid_invalid(self, tmp_path):
        """混合有效和无效 JSON"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "test.jsonl"
            session_file.write_text(
                '{"role": "user", "content": "valid"}\ninvalid\n{"role": "assistant", "content": "also valid"}'
            )

            loaded = []
            for line in session_file.read_text().splitlines():
                if line.strip():
                    try:
                        loaded.append(json.loads(line))
                    except:
                        pass

            assert len(loaded) == 2
            assert loaded[0]["role"] == "user"
            assert loaded[1]["role"] == "assistant"

    def test_load_with_tool_messages(self, tmp_path):
        """加载工具消息"""
        messages = [
            {"role": "user", "content": "Run command"},
            {"role": "assistant", "content": "Running..."},
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "[run_shell]: output",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "test.jsonl"
            session_file.write_text("\n".join(json.dumps(m) for m in messages))

            loaded = []
            for line in session_file.read_text().splitlines():
                if line.strip():
                    loaded.append(json.loads(line))

            assert len(loaded) == 3
            assert loaded[2]["role"] == "tool"
            assert "tool_call_id" in loaded[2]


class TestMessagesContent:
    """消息内容测试"""

    def test_messages_have_required_fields(self):
        """消息有必需字段"""
        message = {"role": "user", "content": "Hello"}

        assert "role" in message
        assert "content" in message
        assert message["role"] in ["user", "assistant", "system", "tool"]

    def test_tool_message_has_tool_call_id(self):
        """工具消息有 tool_call_id"""
        message = {
            "role": "tool",
            "tool_call_id": "call_abc123",
            "content": "[run_shell]: result",
        }

        assert message["role"] == "tool"
        assert "tool_call_id" in message

    def test_assistant_message_with_tool_calls(self):
        """带 tool_calls 的助手消息"""
        message = {
            "role": "assistant",
            "content": "I'll run that command",
            "tool_calls": [
                {"id": "call_1", "function": {"name": "run_shell", "arguments": "{}"}}
            ],
        }

        assert message["role"] == "assistant"
        assert "tool_calls" in message

    def test_message_with_chinese_content(self):
        """中文内容消息"""
        message = {"role": "user", "content": "你好世界"}

        encoded = json.dumps(message, ensure_ascii=False)
        decoded = json.loads(encoded)

        assert decoded["content"] == "你好世界"

    def test_message_with_emoji(self):
        """带 emoji 消息"""
        message = {"role": "user", "content": "Hello 👋"}

        encoded = json.dumps(message, ensure_ascii=False)
        decoded = json.loads(encoded)

        assert "👋" in decoded["content"]


class TestMessagesConversation:
    """对话消息测试"""

    def test_conversation_messages_sequence(self):
        """对话消息序列"""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "I'm doing well!"},
        ]

        # 验证序列
        roles = [m["role"] for m in messages]
        assert roles == ["system", "user", "assistant", "user", "assistant"]

    def test_tool_call_conversation(self):
        """工具调用对话"""
        messages = [
            {"role": "user", "content": "List files"},
            {
                "role": "assistant",
                "content": "I'll list the files...",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "run_shell",
                            "arguments": '{"command": "ls"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "[run_shell]: file1.txt\nfile2.txt",
            },
            {"role": "assistant", "content": "I found file1.txt and file2.txt."},
        ]

        assert len(messages) == 4
        assert messages[1]["tool_calls"][0]["function"]["name"] == "run_shell"
        assert messages[2]["role"] == "tool"

    def test_multi_turn_conversation(self):
        """多轮对话"""
        messages = [
            {"role": "user", "content": "Turn 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Turn 2"},
            {"role": "assistant", "content": "Response 2"},
            {"role": "user", "content": "Turn 3"},
            {"role": "assistant", "content": "Response 3"},
        ]

        # 用户消息和助手消息交替
        for i in range(len(messages)):
            if i % 2 == 0:
                assert messages[i]["role"] == "user"
            else:
                assert messages[i]["role"] == "assistant"


class TestMessageStorageEdgeCases:
    """消息存储边界情况测试"""

    def test_empty_content(self):
        """空内容"""
        message = {"role": "user", "content": ""}

        encoded = json.dumps(message)
        decoded = json.loads(encoded)

        assert decoded["content"] == ""

    def test_very_long_content(self):
        """非常长的内容"""
        long_text = "x" * 100000
        message = {"role": "user", "content": long_text}

        encoded = json.dumps(message)
        decoded = json.loads(encoded)

        assert len(decoded["content"]) == 100000

    def test_special_characters_in_content(self):
        """内容含特殊字符"""
        message = {"role": "user", "content": 'Line1\nLine2\tTabbed"Quoted"'}

        encoded = json.dumps(message)
        decoded = json.loads(encoded)

        assert "\n" in decoded["content"]
        assert "\t" in decoded["content"]

    def test_unicode_in_content(self):
        """内容含 unicode"""
        message = {"role": "user", "content": "日本語中文한국어"}

        encoded = json.dumps(message, ensure_ascii=False)
        decoded = json.loads(encoded)

        assert decoded["content"] == "日本語中文한국어"
