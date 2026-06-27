# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""Prompt 测试"""

import pytest
from core.prompts import format_system_prompt, SYSTEM_PROMPT


class TestSystemPrompt:
    """System Prompt 测试"""

    def test_system_prompt_not_empty(self):
        """System Prompt 不为空"""
        assert SYSTEM_PROMPT is not None
        assert len(SYSTEM_PROMPT) > 0

    def test_system_prompt_contains_core_capabilities(self):
        """System Prompt 包含核心能力说明"""
        assert "run_shell" in SYSTEM_PROMPT
        assert "run_skills" in SYSTEM_PROMPT

    def test_system_prompt_contains_work_modes(self):
        """System Prompt 包含工作模式说明"""
        assert "Talk while doing" in SYSTEM_PROMPT or "think then act" in SYSTEM_PROMPT.lower()
        assert "Think then act" in SYSTEM_PROMPT or "think" in SYSTEM_PROMPT.lower()

    def test_system_prompt_contains_tools_examples(self):
        """System Prompt 包含工具示例"""
        assert "run_shell" in SYSTEM_PROMPT
        assert "ls" in SYSTEM_PROMPT or "cat" in SYSTEM_PROMPT

    def test_system_prompt_contains_flow_control(self):
        """System Prompt 包含流程控制说明"""
        assert "Graph" in SYSTEM_PROMPT or "graph" in SYSTEM_PROMPT
        assert "tool_calls" in SYSTEM_PROMPT

    def test_system_prompt_contains_context_management(self):
        """System Prompt 包含上下文管理说明"""
        assert "session_id" in SYSTEM_PROMPT
        assert "messages.jsonl" in SYSTEM_PROMPT or "messages" in SYSTEM_PROMPT


class TestFormatSystemPrompt:
    """格式化 System Prompt 测试"""

    def test_format_with_skills_list(self):
        """格式化带 skills_list"""
        skills_list = "- current_time: 获取当前时间"
        session_id = "test_session_123"

        prompt = format_system_prompt(skills_list, session_id)

        assert skills_list in prompt

    def test_format_with_session_id(self):
        """格式化带 session_id"""
        skills_list = "- test_skill"
        session_id = "abc123def456"

        prompt = format_system_prompt(skills_list, session_id)

        assert session_id in prompt

    def test_format_replaces_all_placeholders(self):
        """格式化替换所有占位符"""
        skills_list = "- skill1\n- skill2"
        session_id = "session_xyz"

        prompt = format_system_prompt(skills_list, session_id)

        # 检查占位符被替换
        assert "{skills_list}" not in prompt
        assert "{session_id}" not in prompt

    def test_format_preserves_skills_list_content(self):
        """格式化保留 skills_list 内容"""
        skills_list = "- current_time: 获取当前时间\n- calculator: 计算器"
        session_id = "test"

        prompt = format_system_prompt(skills_list, session_id)

        assert "current_time" in prompt
        assert "calculator" in prompt

    def test_format_preserves_session_id_exact(self):
        """格式化保留 session_id 精确值"""
        skills_list = "- test"
        session_id = "unique_session_id_12345"

        prompt = format_system_prompt(skills_list, session_id)

        assert session_id in prompt

    def test_format_with_empty_personality(self):
        """格式化空 personality"""
        skills_list = "- test"
        session_id = "test"

        prompt = format_system_prompt(skills_list, session_id, personality="")

        assert "{personality}" not in prompt

    def test_format_with_personality(self):
        """格式化带 personality"""
        skills_list = "- test"
        session_id = "test"
        personality = "## SOUL\nYou are a helpful assistant."

        prompt = format_system_prompt(skills_list, session_id, personality)

        assert "SOUL" in prompt
        assert personality in prompt

    def test_format_with_workspace_path(self):
        """格式化带 workspace_path"""
        skills_list = "- test"
        session_id = "test"
        ws_path = "/custom/path/to/workspace"

        prompt = format_system_prompt(skills_list, session_id, workspace_path=ws_path)

        assert ws_path in prompt
        assert "{workspace_path}" not in prompt

    def test_format_default_workspace_path(self):
        """默认 workspace_path 为 workspace"""
        skills_list = "- test"
        session_id = "test"

        prompt = format_system_prompt(skills_list, session_id)

        assert "workspace" in prompt
        assert "{workspace_path}" not in prompt


class TestPromptPlaceholders:
    """Prompt 占位符测试"""

    def test_skills_list_placeholder(self):
        """skills_list 占位符"""
        assert "{skills_list}" in SYSTEM_PROMPT

    def test_session_id_placeholder(self):
        """session_id 占位符"""
        assert "{session_id}" in SYSTEM_PROMPT

    def test_workspace_path_placeholder(self):
        """workspace_path 占位符"""
        assert "{workspace_path}" in SYSTEM_PROMPT

    def test_multiple_placeholders(self):
        """多个占位符"""
        assert SYSTEM_PROMPT.count("{") >= 3



class TestPromptContent:
    """Prompt 内容测试"""

    def test_prompt_has_instructions(self):
        """Prompt 包含指令"""
        assert "你是一个" in SYSTEM_PROMPT or "You are" in SYSTEM_PROMPT

    def test_prompt_has_capabilities_section(self):
        """Prompt 有能力说明部分"""
        content_lower = SYSTEM_PROMPT.lower()
        assert "能力" in content_lower or "capabilit" in content_lower

    def test_prompt_has_examples_section(self):
        """Prompt 有示例部分"""
        assert "示例" in SYSTEM_PROMPT or "example" in SYSTEM_PROMPT.lower()

    def test_prompt_has_workflow_section(self):
        """Prompt 有工作流说明"""
        content_lower = SYSTEM_PROMPT.lower()
        assert (
            "工作" in content_lower
            or "mode" in content_lower
            or "flow" in content_lower
        )


class TestPromptFormatting:
    """Prompt 格式化边界测试"""

    def test_format_with_special_chars_in_session_id(self):
        """session_id 包含特殊字符"""
        skills_list = "- test"
        session_id = "session-with-dashes_and_underscores"

        prompt = format_system_prompt(skills_list, session_id)

        assert session_id in prompt

    def test_format_with_unicode_skills(self):
        """skills_list 包含 unicode"""
        skills_list = "- 测试技能：获取测试时间"
        session_id = "test"

        prompt = format_system_prompt(skills_list, session_id)

        assert "测试技能" in prompt

    def test_format_with_empty_skills_list(self):
        """空的 skills_list"""
        skills_list = ""
        session_id = "test"

        prompt = format_system_prompt(skills_list, session_id)

        assert session_id in prompt

    def test_format_with_long_session_id(self):
        """长 session_id"""
        skills_list = "- test"
        session_id = "x" * 100

        prompt = format_system_prompt(skills_list, session_id)

        assert session_id in prompt
