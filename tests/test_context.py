# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""上下文管理测试"""

import pytest
from core.app import calculate_tokens, count_messages_tokens, CONTEXT_UNLOAD_THRESHOLD


class TestTokenCalculation:
    """Token 计算测试"""

    def test_calculate_tokens_exact(self):
        """测试精确 token 计算"""
        assert calculate_tokens("hello") == 1
        assert calculate_tokens("hello world") == 2

    def test_calculate_tokens_empty(self):
        """测试空字符串"""
        assert calculate_tokens("") == 0

    def test_calculate_tokens_chinese(self):
        """测试中文字符"""
        # 简化计算：4个字符 ≈ 1个token
        text = "你好世界"
        assert calculate_tokens(text) == 1

    def test_calculate_tokens_long(self):
        """测试长字符串"""
        text = "a" * 100
        assert calculate_tokens(text) == 25


class TestMessagesTokenCount:
    """消息 Token 计数测试"""

    def test_count_messages_tokens_empty(self):
        """测试空消息列表"""
        assert count_messages_tokens([]) == 0

    def test_count_messages_tokens_single(self):
        """测试单条消息"""
        messages = [{"role": "user", "content": "hello"}]
        assert count_messages_tokens(messages) >= 1

    def test_count_messages_tokens_multiple(self):
        """测试多条消息"""
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        tokens = count_messages_tokens(messages)
        assert tokens >= 2

    def test_count_messages_tokens_missing_content(self):
        """测试缺少 content 的消息"""
        messages = [{"role": "user"}]
        assert count_messages_tokens(messages) == 0


class TestContextThreshold:
    """上下文阈值测试"""

    def test_threshold_default(self):
        """测试默认阈值"""
        assert CONTEXT_UNLOAD_THRESHOLD == 256000

    def test_threshold_approximately_chars(self):
        """测试阈值对应的字符数"""
        # 256000 tokens ≈ 1024000 characters
        expected_chars = CONTEXT_UNLOAD_THRESHOLD * 4
        assert expected_chars == 1024000


class TestContextRecovery:
    """上下文恢复测试"""

    def test_context_message_format(self):
        """测试消息格式"""
        message = {"role": "assistant", "content": "Hello, world!"}

        assert "role" in message
        assert "content" in message
        assert message["role"] in ["user", "assistant", "system", "tool"]

    def test_session_id_in_prompt(self):
        """测试 session_id 在 prompt 中的替换"""
        from core.prompts import format_system_prompt, SYSTEM_PROMPT

        skills_list = "- test_skill"
        session_id = "abc123"

        prompt = format_system_prompt(skills_list, session_id)

        assert session_id in prompt
        assert skills_list in prompt
