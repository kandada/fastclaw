"""核心引擎测试"""

import pytest

from core.app import (
    app,
    run_shell,
    run_skills,
    load_skills,
    calculate_tokens,
    count_messages_tokens,
)


class TestTools:
    """工具测试"""

    @pytest.mark.asyncio
    async def test_run_shell_basic(self):
        """测试 run_shell 基本功能"""
        result = await run_shell("echo 'hello'")
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_run_shell_ls(self):
        """测试 ls 命令"""
        result = await run_shell("ls -la")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_run_shell_error(self):
        """测试命令错误处理"""
        result = await run_shell("exit 1")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_run_skills_list(self):
        """测试列出技能"""
        result = await run_skills("__list__")
        assert isinstance(result, str)


class TestSkills:
    """Skills 测试"""

    def test_load_skills(self):
        """测试加载技能"""
        skills = load_skills("workspace/skills")
        assert isinstance(skills, dict)

    def test_calculate_tokens(self):
        """测试 token 计算"""
        assert calculate_tokens("hello") == 1
        assert calculate_tokens("hello world") == 2

    def test_count_messages_tokens(self):
        """测试消息 token 计数"""
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        tokens = count_messages_tokens(messages)
        assert tokens >= 2


class TestApp:
    """App 测试"""

    def test_app_exists(self):
        """测试 app 存在"""
        assert app is not None

    def test_app_has_tools(self):
        """测试 app 有工具"""
        tools = app.get_tools()
        assert len(tools) >= 2

    def test_app_has_agent(self):
        """测试 app 有 agent"""
        graphs = app._graphs
        assert "main" in graphs

    def test_get_tool_schemas(self):
        """测试获取工具 schema"""
        schemas = app.get_tool_schemas()
        assert isinstance(schemas, list)
        assert len(schemas) >= 2
