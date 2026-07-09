# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""
Skill 优化项独立验证脚本（无需 pytest）。

用法:
    .venv/bin/python fastclaw/tests/manual/verify_skills.py
"""

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.app import (  # noqa: E402
    load_skills,
    execute_skill,
    render_doc_skill,
    find_skill_md,
    find_skill_entry,
    parse_skill_description,
    list_skill_resources,
)

PASS, FAIL = 0, 0


def check(label, cond, detail=""):
    global PASS, FAIL
    mark = "✅" if cond else "❌"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"  {mark} {label}" + (f"  ({detail})" if detail and not cond else ""))


def mkskill(base, name, md, main_py=None, extra=None, md_name="SKILL.md"):
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / md_name).write_text(md, encoding="utf-8")
    if main_py is not None:
        (d / "main.py").write_text(main_py, encoding="utf-8")
    for rel, c in (extra or {}).items():
        f = d / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(c, encoding="utf-8")
    return d


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="skill_verify_"))
    print(f"临时目录: {tmp}\n")

    print("[1] execute_skill 无脚本回退返回 SKILL.md")
    d = mkskill(tmp, "doc1", "## Workflow\ndo the thing")
    out = await execute_skill("doc1", skill_dir=str(d))
    check("返回文档内容而非 not found", "do the thing" in out and not out.startswith("Error:"))

    print("[2] 文件名大小写健壮 (skill.md)")
    d = mkskill(tmp, "low", "## Description\nlower", md_name="skill.md")
    check("find_skill_md 定位 skill.md", find_skill_md(d) is not None)
    check("load_skills 加载 skill.md 技能", "low" in load_skills(str(tmp)))

    print("[3] Description 解析升级")
    check("frontmatter description",
          parse_skill_description("---\ndescription: FM desc\n---\nbody") == "FM desc")
    check("多行 ## Description",
          parse_skill_description("## Description\nL1\nL2\n\n## X") == "L1 L2")
    check("大小写不敏感标题",
          parse_skill_description("## description\nlow") == "low")

    print("[4] 文档型技能模板存在且可解析")
    seed = Path(__file__).resolve().parents[2] / "workspace_seed" / "skills" / "user" / "_template_doc"
    tpl = seed / "SKILL.md"
    check("_template_doc/SKILL.md 存在", tpl.exists())
    if tpl.exists():
        desc = parse_skill_description(tpl.read_text(encoding="utf-8"))
        check("模板 frontmatter description 可解析", bool(desc), desc)

    print("[5] System Prompt 含文档技能说明")
    from core.prompts import SYSTEM_PROMPT
    check("提示区分 script/document 技能", "Document skills" in SYSTEM_PROMPT)

    print("[6] params 静默丢弃提示")
    d = mkskill(tmp, "doc2", "## Workflow\nx")
    out = await execute_skill("doc2", params={"foo": "bar"}, skill_dir=str(d))
    check("提示 document-only + 参数名", "document-only skill" in out and "foo" in out)

    print("[7] __info__/execute 语义定位文档化")
    check("提示含 Semantic note", "Semantic note" in SYSTEM_PROMPT)

    print("[8] 复杂技能资源清单自动披露")
    d = mkskill(tmp, "doc3", "## Workflow\nx",
                extra={"reference.md": "r", "scripts/run.sh": "echo", "__pycache__/a.pyc": "b"})
    res = list_skill_resources(d)
    check("列出 reference.md / scripts", "reference.md" in res and "scripts/run.sh" in res)
    check("排除 __pycache__", all("__pycache__" not in r for r in res))
    out = render_doc_skill("doc3", d)
    check("execute 输出含资源清单", "Available Resources" in out and "reference.md" in out)

    print("\n[回归] 脚本技能仍正常执行")
    d = mkskill(tmp, "script1", "## Description\nx",
                main_py="async def execute(**kw):\n    return 'ran-ok'\n")
    out = await execute_skill("script1", skill_dir=str(d))
    check("main.py execute() 正常运行", out == "ran-ok")

    print("\n[9] 非 main.py 的唯一 .py 作为入口")
    d = mkskill(tmp, "named", "## Description\nx")
    (d / "do_stuff.py").write_text("async def execute(**kw):\n    return 'named-ran'\n", encoding="utf-8")
    check("find_skill_entry 命中 do_stuff.py", find_skill_entry(d).name == "do_stuff.py")
    out = await execute_skill("named", skill_dir=str(d))
    check("唯一命名脚本被执行", out == "named-ran")

    d = mkskill(tmp, "mainfirst", "## Description\nx",
                main_py="async def execute():\n    return 'from-main'\n")
    (d / "helper.py").write_text("x=1\n", encoding="utf-8")
    check("main.py 优先于其他 .py", find_skill_entry(d).name == "main.py")

    d = mkskill(tmp, "amb", "## Workflow\nguide")
    (d / "a.py").write_text("async def execute():\n    return 'a'\n", encoding="utf-8")
    (d / "b.py").write_text("async def execute():\n    return 'b'\n", encoding="utf-8")
    check("多个 .py 视为歧义 → None", find_skill_entry(d) is None)
    out = await execute_skill("amb", skill_dir=str(d))
    check("歧义时回退文档", "guide" in out and not out.startswith("Error:"))

    d = mkskill(tmp, "under", "## Description\nx")
    (d / "__init__.py").write_text("", encoding="utf-8")
    (d / "entry.py").write_text("async def execute():\n    return 'e'\n", encoding="utf-8")
    check("下划线开头的 .py 被忽略", find_skill_entry(d).name == "entry.py")


    print("\n[真实种子] 加载 workspace_seed/skills")
    real = Path(__file__).resolve().parents[2] / "workspace_seed" / "skills"
    skills = load_skills(str(real))
    check("加载到预置技能", len(skills) >= 7, f"{sorted(skills)}")
    check("含新文档模板 _template_doc", "_template_doc" in skills)

    print(f"\n{'='*40}\n结果: {PASS} passed, {FAIL} failed\n{'='*40}")
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
