# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""Skills 管理 & 热重载 & CRUD API 测试"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# — helpers —


def _setup_skills_workspace():
    """创建临时 workspace，设置环境变量，返回 ws 路径"""
    ws = tempfile.mkdtemp()
    (Path(ws) / "skills" / "bundled").mkdir(parents=True, exist_ok=True)
    (Path(ws) / "skills" / "user").mkdir(parents=True, exist_ok=True)
    os.environ["FASTCLAW_WORKSPACE"] = ws

    # 清除所有可能已缓存的模块，确保后续 import 使用新 workspace
    targets = [
        "core.app", "core.config", "core.prompts", "core.paths", "core.bootstrap",
        "gateway.router", "gateway.server", "gateway.event_bus",
        "fastclaw.core.app", "fastclaw.core.config", "fastclaw.core.prompts",
        "fastclaw.core.paths", "fastclaw.core.bootstrap",
        "fastclaw.gateway.router", "fastclaw.gateway.server", "fastclaw.gateway.event_bus",
    ]
    for mod in targets:
        sys.modules.pop(mod, None)

    # 确保 fastclaw 包路径可用
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    return ws


def _make_skill_md(ws, sub, name, content):
    d = Path(ws) / "skills" / sub / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(content, encoding="utf-8")
    return d


def _make_skill_script(ws, sub, name, md_content, py_code):
    d = Path(ws) / "skills" / sub / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(md_content, encoding="utf-8")
    (d / "main.py").write_text(py_code, encoding="utf-8")
    return d


# — load_skills / hot‑reload —


class TestLoadSkillsExcludeUnderscore:
    def test_underscore_excluded(self):
        ws = _setup_skills_workspace()
        _make_skill_md(ws, "user", "_template", "## Description\ntemplate")
        _make_skill_md(ws, "user", "my_skill", "## Description\nmine")

        from fastclaw.core.app import load_skills

        skills = load_skills()
        assert "my_skill" in skills
        assert "_template" not in skills
        assert len(skills) == 1

    def test_bundled_underscore_also_excluded(self):
        ws = _setup_skills_workspace()
        _make_skill_md(ws, "bundled", "__hidden", "## Description\nhidden")

        from fastclaw.core.app import load_skills

        skills = load_skills()
        assert "__hidden" not in skills


class TestHotRegister:
    def test_new_skill_detected(self):
        ws = _setup_skills_workspace()
        _make_skill_md(ws, "bundled", "alpha", "## Description\nalpha")
        from fastclaw.core.app import _try_register_skill, SKILLS

        # freshly imported SKILLS should contain alpha
        assert "alpha" in SKILLS

        _make_skill_md(ws, "user", "beta", "## Description\nbeta")
        assert "beta" not in SKILLS
        ok = _try_register_skill("beta")
        assert ok
        assert "beta" in SKILLS
        assert SKILLS["beta"]["description"] == "beta"

    def test_nonexistent_returns_false(self):
        ws = _setup_skills_workspace()
        from fastclaw.core.app import _try_register_skill

        assert not _try_register_skill("no_such_skill")

    def test_case_insensitive_filename(self):
        ws = _setup_skills_workspace()
        d = Path(ws) / "skills" / "user" / "case_test"
        d.mkdir(parents=True, exist_ok=True)
        (d / "skill.md").write_text("## Description\nlowercase", encoding="utf-8")

        from fastclaw.core.app import _try_register_skill, SKILLS

        _try_register_skill("case_test")
        assert "case_test" in SKILLS


# — run_skills __list__ refresh —


class TestRunSkillsListRefresh:
    @pytest.mark.asyncio
    async def test_list_picks_up_new_skill(self):
        ws = _setup_skills_workspace()
        _make_skill_md(ws, "bundled", "old_one", "## Description\nold")
        from fastclaw.core.app import SKILLS, run_skills

        assert "old_one" in SKILLS

        _make_skill_md(ws, "user", "fresh_one", "## Description\nfresh")

        result = await run_skills("__list__")
        assert "fresh_one" in SKILLS
        assert "fresh_one" in result

    @pytest.mark.asyncio
    async def test_list_removes_deleted_skill(self):
        ws = _setup_skills_workspace()
        d = _make_skill_md(ws, "user", "temp_skill", "## Description\ntemp")
        from fastclaw.core.app import SKILLS, run_skills

        # delete from disk
        (d / "SKILL.md").unlink()
        d.rmdir()

        result = await run_skills("__list__")
        assert "temp_skill" not in result
        assert "temp_skill" not in SKILLS

    @pytest.mark.asyncio
    async def test_list_excludes_underscore(self):
        ws = _setup_skills_workspace()
        _make_skill_md(ws, "user", "_hidden", "## Description\nhidden")
        _make_skill_md(ws, "user", "visible", "## Description\nvisible")
        from fastclaw.core.app import run_skills

        result = await run_skills("__list__")
        assert "_hidden" not in result
        assert "visible" in result


# — parse_skill_sections code-fence —


class TestParseSkillSections:
    def test_skips_code_fence_sections(self):
        ws = _setup_skills_workspace()
        from fastclaw.gateway.router import _parse_skill_sections

        content = (
            "## Description\nA meta skill\n\n"
            "## Parameters\n- name: name\n\n"
            "## Example\nrun_skills(\"meta\")\n\n"
            "```markdown\n"
            "## Remote Endpoint\nhttps://fake.in.block/api\n\n"
            "## Secret\nsecret_in_block\n"
            "```\n\n"
            "## Rules\n- rule one"
        )
        sections = _parse_skill_sections(content)
        assert "Remote Endpoint" not in sections
        assert "Secret" not in sections
        assert sections["Description"] == "A meta skill"
        assert "rule one" in sections["Rules"]

    def test_real_remote_endpoint_still_parsed(self):
        ws = _setup_skills_workspace()
        from fastclaw.gateway.router import _parse_skill_sections

        content = (
            "## Description\nRemote skill\n\n"
            "## Parameters\n- url: URL\n\n"
            "## Example\nrun_skills(\"remote\")\n\n"
            "## Remote Endpoint\nhttps://real.api.com\n\n"
            "## Secret\nreal_key_123"
        )
        sections = _parse_skill_sections(content)
        assert sections["Remote Endpoint"] == "https://real.api.com"
        assert sections["Secret"] == "real_key_123"


# — API CRUD —


class TestSkillsApiList:
    @pytest.mark.asyncio
    async def test_lists_bundled_and_user(self):
        ws = _setup_skills_workspace()
        _make_skill_md(ws, "bundled", "b_one", "## Description\nbundled")
        _make_skill_md(ws, "user", "u_one", "## Description\nuser")
        from fastclaw.gateway.router import list_user_skills

        result = await list_user_skills()
        skills = result["skills"]
        names = [s["name"] for s in skills]
        assert "b_one" in names
        assert "u_one" in names
        for s in skills:
            if s["name"] == "b_one":
                assert s["is_bundled"]
            if s["name"] == "u_one":
                assert not s["is_bundled"]

    @pytest.mark.asyncio
    async def test_excludes_underscore(self):
        ws = _setup_skills_workspace()
        _make_skill_md(ws, "user", "_template", "## Description\ntemplate")
        _make_skill_md(ws, "user", "real_skill", "## Description\nreal")
        from fastclaw.gateway.router import list_user_skills

        result = await list_user_skills()
        names = [s["name"] for s in result["skills"]]
        assert "_template" not in names
        assert "real_skill" in names

    @pytest.mark.asyncio
    async def test_detects_has_secret_and_endpoint(self):
        ws = _setup_skills_workspace()
        _make_skill_md(ws, "user", "with_ep", (
            "## Description\nx\n## Remote Endpoint\nhttps://api.x.com\n## Secret\nkey42"
        ))
        _make_skill_md(ws, "user", "no_ep", "## Description\nplain")
        from fastclaw.gateway.router import list_user_skills

        result = await list_user_skills()
        by_name = {s["name"]: s for s in result["skills"]}
        assert by_name["with_ep"]["endpoint"] == "https://api.x.com"
        assert by_name["with_ep"]["has_secret"] is True
        assert by_name["no_ep"]["endpoint"] == ""
        assert by_name["no_ep"]["has_secret"] is False


class TestSkillsApiCreate:
    @pytest.mark.asyncio
    async def test_create_document_skill(self):
        ws = _setup_skills_workspace()
        from fastclaw.gateway.router import create_user_skill

        result = await create_user_skill({
            "name": "my_new",
            "description": "A new skill",
            "parameters": "- x: x",
            "example": 'run_skills("my_new")',
            "endpoint": "https://api.example.com",
            "secret": "sk-123",
        })
        assert result["status"] == "created"
        md = (Path(ws) / "skills" / "user" / "my_new" / "SKILL.md").read_text()
        assert "A new skill" in md
        assert "https://api.example.com" in md
        assert "sk-123" in md

    @pytest.mark.asyncio
    async def test_create_without_optional_fields(self):
        ws = _setup_skills_workspace()
        from fastclaw.gateway.router import create_user_skill

        await create_user_skill({
            "name": "simple",
            "description": "Simple",
            "parameters": "",
            "example": "run_skills(\"simple\")",
        })
        md = (Path(ws) / "skills" / "user" / "simple" / "SKILL.md").read_text()
        assert "Remote Endpoint" not in md
        assert "Secret" not in md

    @pytest.mark.asyncio
    async def test_rejects_bad_name(self):
        ws = _setup_skills_workspace()
        from fastclaw.gateway.router import create_user_skill
        from fastapi import HTTPException

        for bad in ["Bad Name", "UPPERCASE", "-dash"]:
            with pytest.raises(HTTPException) as exc:
                await create_user_skill({"name": bad, "description": "x", "parameters": "", "example": ""})
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rejects_bundled_conflict(self):
        ws = _setup_skills_workspace()
        _make_skill_md(ws, "bundled", "feishu", "## Description\nfeishu")
        from fastclaw.gateway.router import create_user_skill
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await create_user_skill({"name": "feishu", "description": "x", "parameters": "", "example": ""})
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_rejects_duplicate(self):
        ws = _setup_skills_workspace()
        _make_skill_md(ws, "user", "dup", "## Description\ndup")
        from fastclaw.gateway.router import create_user_skill
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await create_user_skill({"name": "dup", "description": "x", "parameters": "", "example": ""})
        assert exc.value.status_code == 409


class TestSkillsApiGet:
    @pytest.mark.asyncio
    async def test_get_user_skill(self):
        ws = _setup_skills_workspace()
        _make_skill_md(ws, "user", "my_test", "## Description\nUser desc")
        from fastclaw.gateway.router import get_user_skill

        result = await get_user_skill("my_test")
        assert result["name"] == "my_test"
        assert result["description"] == "User desc"
        assert result["is_bundled"] is False

    @pytest.mark.asyncio
    async def test_get_bundled_skill(self):
        ws = _setup_skills_workspace()
        _make_skill_md(ws, "bundled", "builtin", "## Description\nBuiltin desc")
        from fastclaw.gateway.router import get_user_skill

        result = await get_user_skill("builtin")
        assert result["name"] == "builtin"
        assert result["is_bundled"] is True

    @pytest.mark.asyncio
    async def test_not_found(self):
        ws = _setup_skills_workspace()
        from fastclaw.gateway.router import get_user_skill
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await get_user_skill("no_such")
        assert exc.value.status_code == 404


class TestSkillsApiUpdate:
    @pytest.mark.asyncio
    async def test_update_skill(self):
        ws = _setup_skills_workspace()
        _make_skill_md(ws, "user", "edit_me", "## Description\nOld desc")
        from fastclaw.gateway.router import update_user_skill

        result = await update_user_skill("edit_me", {
            "name": "edit_me",
            "description": "New desc",
            "parameters": "- a: a",
            "example": "run_skills(\"edit_me\")",
        })
        assert result["status"] == "updated"
        md = (Path(ws) / "skills" / "user" / "edit_me" / "SKILL.md").read_text()
        assert "New desc" in md

    @pytest.mark.asyncio
    async def test_update_preserves_secret_when_empty(self):
        ws = _setup_skills_workspace()
        _make_skill_md(ws, "user", "with_secret", (
            "## Description\nSecret skill\n## Secret\npreserved_key"
        ))
        from fastclaw.gateway.router import update_user_skill

        await update_user_skill("with_secret", {
            "name": "with_secret",
            "description": "Updated",
            "parameters": "",
            "example": "",
            "secret": "",
        })
        md = (Path(ws) / "skills" / "user" / "with_secret" / "SKILL.md").read_text()
        assert "preserved_key" in md

    @pytest.mark.asyncio
    async def test_rejects_update_bundled(self):
        ws = _setup_skills_workspace()
        _make_skill_md(ws, "bundled", "bundled_skill", "## Description\nbundled")
        from fastclaw.gateway.router import update_user_skill
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await update_user_skill("bundled_skill", {"name": "bundled_skill", "description": "hacked"})
        assert exc.value.status_code == 403


class TestSkillsApiDelete:
    @pytest.mark.asyncio
    async def test_delete_user_skill(self):
        ws = _setup_skills_workspace()
        _make_skill_md(ws, "user", "del_me", "## Description\ndel")
        from fastclaw.gateway.router import delete_user_skill

        result = await delete_user_skill("del_me")
        assert result["status"] == "deleted"
        assert not (Path(ws) / "skills" / "user" / "del_me").exists()

    @pytest.mark.asyncio
    async def test_rejects_delete_bundled(self):
        ws = _setup_skills_workspace()
        _make_skill_md(ws, "bundled", "bundled_skill", "## Description\nbundled")
        from fastclaw.gateway.router import delete_user_skill
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await delete_user_skill("bundled_skill")
        assert exc.value.status_code == 403


# — generate_skill_md —


class TestGenerateSkillMd:
    def test_generates_required_sections(self):
        ws = _setup_skills_workspace()
        from fastclaw.gateway.router import _generate_skill_md

        md = _generate_skill_md("My desc", "- x: x", "run_skills(\"x\")")
        assert "## Description\nMy desc" in md
        assert "## Parameters\n- x: x" in md
        assert "## Example\nrun_skills(\"x\")" in md
        assert "Remote Endpoint" not in md
        assert "Secret" not in md

    def test_appends_optional_fields(self):
        ws = _setup_skills_workspace()
        from fastclaw.gateway.router import _generate_skill_md

        md = _generate_skill_md("desc", "- x", "ex", endpoint="https://api.com", secret="key")
        assert "## Remote Endpoint\nhttps://api.com" in md
        assert "## Secret\nkey" in md

    def test_skips_empty_optional(self):
        ws = _setup_skills_workspace()
        from fastclaw.gateway.router import _generate_skill_md

        md = _generate_skill_md("desc", "- x", "ex", endpoint="", secret="  ")
        assert "Remote Endpoint" not in md
        assert "Secret" not in md
