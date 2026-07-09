# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""Skill 加载/执行相关测试：文档型技能、大小写健壮性、frontmatter 解析、资源披露"""

import pytest

from core.app import (
    load_skills,
    execute_skill,
    render_doc_skill,
    find_skill_md,
    find_skill_entry,
    parse_skill_description,
    list_skill_resources,
)


def _make_skill(base, name, md_content, main_py=None, extra=None, md_filename="SKILL.md"):
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / md_filename).write_text(md_content, encoding="utf-8")
    if main_py is not None:
        (d / "main.py").write_text(main_py, encoding="utf-8")
    for rel, content in (extra or {}).items():
        f = d / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
    return d


class TestParseDescription:
    def test_frontmatter_description(self):
        content = "---\nname: foo\ndescription: Hello from frontmatter\n---\n## Description\nignored line\n"
        assert parse_skill_description(content) == "Hello from frontmatter"

    def test_frontmatter_quoted(self):
        content = '---\ndescription: "Quoted desc"\n---\nbody'
        assert parse_skill_description(content) == "Quoted desc"

    def test_heading_single_line(self):
        content = "## Description\nSingle line desc\n\n## Parameters\n- x"
        assert parse_skill_description(content) == "Single line desc"

    def test_heading_multi_line(self):
        content = "## Description\nLine one\nLine two\n\n## Parameters"
        assert parse_skill_description(content) == "Line one Line two"

    def test_case_insensitive_heading(self):
        content = "## description\nlower heading\n"
        assert parse_skill_description(content) == "lower heading"

    def test_empty(self):
        assert parse_skill_description("no description here") == ""


class TestFindSkillMd:
    def test_uppercase(self, tmp_path):
        d = _make_skill(tmp_path, "s1", "## Description\nx")
        assert find_skill_md(d).name == "SKILL.md"

    def test_lowercase(self, tmp_path):
        d = _make_skill(tmp_path, "s2", "## Description\nx", md_filename="skill.md")
        found = find_skill_md(d)
        assert found is not None and found.name.lower() == "skill.md"

    def test_missing(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        assert find_skill_md(d) is None


class TestLoadSkills:
    def test_loads_doc_and_script(self, tmp_path):
        _make_skill(tmp_path, "doc_skill", "---\ndescription: Doc skill desc\n---\nbody")
        _make_skill(
            tmp_path, "script_skill",
            "## Description\nScript skill desc",
            main_py="async def execute():\n    return 'ok'\n",
        )
        skills = load_skills(str(tmp_path))
        assert set(skills) == {"doc_skill", "script_skill"}
        assert skills["doc_skill"]["description"] == "Doc skill desc"
        assert skills["script_skill"]["description"] == "Script skill desc"

    def test_lowercase_filename_still_loaded(self, tmp_path):
        _make_skill(tmp_path, "low", "## Description\nlow desc", md_filename="skill.md")
        skills = load_skills(str(tmp_path))
        assert "low" in skills

    def test_missing_description_fallback(self, tmp_path):
        _make_skill(tmp_path, "nodesc", "just some text, no headings")
        skills = load_skills(str(tmp_path))
        assert skills["nodesc"]["description"] == "nodesc skill"

    def test_nested_dirs(self, tmp_path):
        _make_skill(tmp_path / "bundled", "a", "## Description\nA")
        _make_skill(tmp_path / "user", "b", "## Description\nB")
        skills = load_skills(str(tmp_path))
        assert {"a", "b"} <= set(skills)


class TestResources:
    def test_lists_resources_excluding_skill_md(self, tmp_path):
        d = _make_skill(
            tmp_path, "res", "## Description\nx",
            extra={"reference.md": "ref", "scripts/run.sh": "echo hi"},
        )
        res = list_skill_resources(d)
        assert "reference.md" in res
        assert "scripts/run.sh" in res
        assert all("skill.md" not in r.lower() for r in res)

    def test_skips_hidden_and_pycache(self, tmp_path):
        d = _make_skill(
            tmp_path, "res2", "## Description\nx",
            extra={"__pycache__/x.pyc": "b", ".hidden": "h", "keep.txt": "k"},
        )
        res = list_skill_resources(d)
        assert res == ["keep.txt"]


class TestFindSkillEntry:
    def test_prefers_main_py(self, tmp_path):
        d = _make_skill(tmp_path, "e1", "## Description\nx", main_py="async def execute():\n    return 1\n")
        (d / "helper.py").write_text("x = 1\n", encoding="utf-8")
        assert find_skill_entry(d).name == "main.py"

    def test_single_other_py(self, tmp_path):
        d = _make_skill(tmp_path, "e2", "## Description\nx")
        (d / "run_it.py").write_text("async def execute():\n    return 1\n", encoding="utf-8")
        assert find_skill_entry(d).name == "run_it.py"

    def test_multiple_py_is_ambiguous(self, tmp_path):
        d = _make_skill(tmp_path, "e3", "## Description\nx")
        (d / "a.py").write_text("x=1\n", encoding="utf-8")
        (d / "b.py").write_text("y=2\n", encoding="utf-8")
        assert find_skill_entry(d) is None

    def test_underscore_ignored(self, tmp_path):
        d = _make_skill(tmp_path, "e4", "## Description\nx")
        (d / "__init__.py").write_text("", encoding="utf-8")
        (d / "entry.py").write_text("async def execute():\n    return 1\n", encoding="utf-8")
        assert find_skill_entry(d).name == "entry.py"

    def test_no_py_is_doc(self, tmp_path):
        d = _make_skill(tmp_path, "e5", "## Workflow\nx")
        assert find_skill_entry(d) is None

    def test_py_in_subdir_not_entry(self, tmp_path):
        d = _make_skill(tmp_path, "e6", "## Workflow\nx", extra={"scripts/tool.py": "x=1\n"})
        assert find_skill_entry(d) is None


class TestRenderDocSkill:
    def test_returns_content(self, tmp_path):
        d = _make_skill(tmp_path, "doc", "## Workflow\nstep 1")
        out = render_doc_skill("doc", d)
        assert "## Workflow" in out

    def test_includes_resources(self, tmp_path):
        d = _make_skill(tmp_path, "doc", "## Workflow\nx", extra={"reference.md": "r"})
        out = render_doc_skill("doc", d)
        assert "Available Resources" in out
        assert "reference.md" in out

    def test_params_note(self, tmp_path):
        d = _make_skill(tmp_path, "doc", "## Workflow\nx")
        out = render_doc_skill("doc", d, params={"foo": "bar"})
        assert "document-only skill" in out
        assert "foo" in out

    def test_missing_md_errors(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        out = render_doc_skill("empty", d)
        assert out.startswith("Error:")


@pytest.mark.asyncio
class TestExecuteSkill:
    async def test_script_skill_runs(self, tmp_path):
        d = _make_skill(
            tmp_path, "s", "## Description\nx",
            main_py="async def execute(**kw):\n    return 'ran'\n",
        )
        out = await execute_skill("s", skill_dir=str(d))
        assert out == "ran"

    async def test_doc_skill_returns_md(self, tmp_path):
        d = _make_skill(tmp_path, "doc", "## Workflow\ndo the thing")
        out = await execute_skill("doc", skill_dir=str(d))
        assert "do the thing" in out
        assert not out.startswith("Error:")

    async def test_doc_skill_with_params_note(self, tmp_path):
        d = _make_skill(tmp_path, "doc", "## Workflow\nx")
        out = await execute_skill("doc", params={"a": 1}, skill_dir=str(d))
        assert "document-only skill" in out

    async def test_nonexistent_dir(self, tmp_path):
        out = await execute_skill("ghost", skill_dir=str(tmp_path / "ghost"))
        assert out.startswith("Error:")

    async def test_single_named_script_runs(self, tmp_path):
        d = _make_skill(tmp_path, "named", "## Description\nx")
        (d / "do_stuff.py").write_text("async def execute(**kw):\n    return 'named-ran'\n", encoding="utf-8")
        out = await execute_skill("named", skill_dir=str(d))
        assert out == "named-ran"

    async def test_ambiguous_scripts_fall_back_to_doc(self, tmp_path):
        d = _make_skill(tmp_path, "amb", "## Workflow\nguide")
        (d / "a.py").write_text("async def execute():\n    return 'a'\n", encoding="utf-8")
        (d / "b.py").write_text("async def execute():\n    return 'b'\n", encoding="utf-8")
        out = await execute_skill("amb", skill_dir=str(d))
        assert "guide" in out and not out.startswith("Error:")

