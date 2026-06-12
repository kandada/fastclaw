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


def _skills_dir():
    candidates = [
        Path(__file__).parent.parent.parent / "workspace" / "skills",
        Path("workspace") / "skills",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    pytest.skip("skills directory not found")


class TestRunShell:
    """run_shell 工具测试"""

    @pytest.mark.asyncio
    async def test_basic(self):
        result = await run_shell("echo 'hello'")
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_ls(self):
        result = await run_shell("ls -la")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_error(self):
        result = await run_shell("exit 1")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_timeout(self):
        result = await run_shell("sleep 100")
        assert "timed out" in result.lower() or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_long_output(self):
        result = await run_shell("python -c 'print(\"x\"*10000)'")
        assert len(result) <= 8100


class TestRunSkills:
    """run_skills 工具测试"""

    @pytest.mark.asyncio
    async def test_list(self):
        result = await run_skills("__list__")
        assert isinstance(result, str)
        assert "current_time" in result

    @pytest.mark.asyncio
    async def test_info(self):
        result = await run_skills("__info__", {"skill_name": "current_time"})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_execute(self):
        result = await run_skills("current_time")
        assert isinstance(result, str)
        assert "-" in result or ":" in result

    @pytest.mark.asyncio
    async def test_not_found(self):
        result = await run_skills("nonexistent_skill")
        assert "not found" in result.lower() or "error" in result.lower()


class TestSkillsLoader:
    """Skills 加载器测试"""

    def test_load_skills(self):
        skills = load_skills(_skills_dir())
        assert isinstance(skills, dict)
        assert "current_time" in skills

    def test_skills_structure(self):
        skills = load_skills(_skills_dir())
        if "current_time" in skills:
            skill = skills["current_time"]
            assert "name" in skill
            assert "description" in skill
            assert "path" in skill


class TestContextManagement:
    """上下文管理测试"""

    def test_calculate_tokens(self):
        assert calculate_tokens("hello") == 1
        assert calculate_tokens("hello world") == 2
        assert calculate_tokens("") == 0

    def test_count_messages_tokens(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        tokens = count_messages_tokens(messages)
        assert tokens >= 2

    def test_empty_messages(self):
        assert count_messages_tokens([]) == 0
