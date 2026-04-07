"""工具测试"""

import pytest
from pathlib import Path
from core.app import (
    run_shell,
    run_skills,
    load_skills,
    calculate_tokens,
    count_messages_tokens,
)


class TestRunShell:
    """run_shell 工具测试"""

    @pytest.mark.asyncio
    async def test_basic(self):
        """基本命令执行"""
        result = await run_shell("echo 'hello'")
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_ls(self):
        """ls 命令"""
        result = await run_shell("ls -la")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_error(self):
        """错误处理"""
        result = await run_shell("exit 1")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_timeout(self):
        """超时测试"""
        result = await run_shell("sleep 100")
        assert "timed out" in result.lower() or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_long_output(self):
        """长输出截断"""
        result = await run_shell("python -c 'print(\"x\"*10000)'")
        assert len(result) <= 5000


class TestRunSkills:
    """run_skills 工具测试"""

    @pytest.mark.asyncio
    async def test_list(self):
        """列出技能"""
        result = await run_skills("__list__")
        assert isinstance(result, str)
        assert "current_time" in result

    @pytest.mark.asyncio
    async def test_info(self):
        """技能详情"""
        result = await run_skills("__info__", {"skill_name": "current_time"})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_execute(self):
        """执行技能"""
        result = await run_skills("current_time")
        assert isinstance(result, str)
        # 应该返回日期时间格式
        assert "-" in result or ":" in result

    @pytest.mark.asyncio
    async def test_not_found(self):
        """不存在的技能"""
        result = await run_skills("nonexistent_skill")
        assert "not found" in result.lower() or "error" in result.lower()


class TestSkillsLoader:
    """Skills 加载器测试"""

    def test_load_skills(self):
        """测试加载技能"""
        skills = load_skills(
            str(Path(__file__).parent.parent.parent / "workspace/skills")
        )
        assert isinstance(skills, dict)
        assert "current_time" in skills

    def test_skills_structure(self):
        """技能结构"""
        skills = load_skills(
            str(Path(__file__).parent.parent.parent / "workspace/skills")
        )
        if "current_time" in skills:
            skill = skills["current_time"]
            assert "name" in skill
            assert "description" in skill
            assert "path" in skill


class TestContextManagement:
    """上下文管理测试"""

    def test_calculate_tokens(self):
        """Token 计算"""
        assert calculate_tokens("hello") == 1
        assert calculate_tokens("hello world") == 2
        assert calculate_tokens("") == 0

    def test_count_messages_tokens(self):
        """消息 Token 计数"""
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        tokens = count_messages_tokens(messages)
        assert tokens >= 2

    def test_empty_messages(self):
        """空消息"""
        assert count_messages_tokens([]) == 0
