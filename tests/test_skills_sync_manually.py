#!/usr/bin/env python3
"""Manual test: verify GitHub skills sync feature.

Usage:
    python3 fastclaw/tests/test_skills_sync_manually.py

What it does:
    1. Creates a temporary empty workspace
    2. Runs sync_skills_if_missing (same as `fastclaw start`)
    3. Shows what was downloaded
    4. Optionally cleans up
"""

import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastclaw.core.skills_sync import sync_skills_if_missing


def main():
    print("=" * 60)
    print("FastClaw Skills Sync — Manual Test")
    print("=" * 60)

    tmpdir = Path(tempfile.mkdtemp(prefix="fastclaw_skills_test_"))
    skills_dir = tmpdir / "skills"
    skills_dir.mkdir(parents=True)

    print(f"\nTemp workspace: {tmpdir}")
    print(f"Skills dir:     {skills_dir} (empty)")
    print("\nCalling sync_skills_if_missing()...\n")

    sync_skills_if_missing(tmpdir)

    print("\n--- Result ---")
    md_files = sorted(skills_dir.rglob("SKILL.md"))
    py_files = sorted(skills_dir.rglob("main.py"))

    if not md_files and not py_files:
        print("  No skills were downloaded.")
        print("  Possible reasons:")
        print("    - No network / GitHub unreachable")
        print("    - GitHub API rate limit")
        print("    - Version tag not found")
    else:
        for f in md_files:
            rel = f.relative_to(tmpdir)
            desc_line = ""
            content = f.read_text()
            for line in content.splitlines():
                if line.strip().startswith("## Description"):
                    idx = content.splitlines().index(line)
                    if idx + 1 < len(content.splitlines()):
                        desc_line = content.splitlines()[idx + 1].strip()
                    break
            print(f"  📄 {rel}" + (f"  — {desc_line}" if desc_line else ""))
        for f in py_files:
            rel = f.relative_to(tmpdir)
            print(f"  🐍 {rel}")

        print(f"\n  Total: {len(md_files)} skill(s), {len(py_files)} file(s)")

    keep = input(f"\nKeep temp workspace [{tmpdir}]? [y/N]: ").strip().lower()
    if keep in ("y", "yes"):
        print(f"  Kept: {tmpdir}")
    else:
        shutil.rmtree(tmpdir)
        print("  Cleaned up.")

    print("\nDone.")


if __name__ == "__main__":
    main()
