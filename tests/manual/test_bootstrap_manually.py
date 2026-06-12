#!/usr/bin/env python3
"""Manual test: verify workspace seed copy.

Usage:
    python3 fastclaw/tests/manual/test_bootstrap_manually.py

What it does:
    1. Creates a temporary empty workspace
    2. Runs copy_seed_files (same as `fastclaw start`)
    3. Shows what was copied
    4. Optionally cleans up
"""

import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastclaw.core.bootstrap import copy_seed_files


def main():
    print("=" * 60)
    print("FastClaw Workspace Seed Copy — Manual Test")
    print("=" * 60)

    tmpdir = Path(tempfile.mkdtemp(prefix="fastclaw_seed_test_"))

    print(f"\nTemp workspace: {tmpdir}")
    print("\nCalling copy_seed_files()...\n")

    copy_seed_files(tmpdir)

    print("\n--- Result ---")
    all_files = sorted(tmpdir.rglob("*"))
    for f in all_files:
        if f.is_dir():
            continue
        rel = f.relative_to(tmpdir)
        print(f"  📄 {rel}")

    if not list(tmpdir.rglob("*")):
        print("  No files were copied.")
        print("  Possible reason: workspace_seed/ not found in package")
    else:
        skill_count = len(list((tmpdir / "skills" / "bundled").rglob("main.py")))
        agent_count = len(list((tmpdir / "data" / "agents").iterdir()))
        print(f"\n  Total: {skill_count} skill(s), {agent_count} agent(s)")

    keep = input(f"\nKeep temp workspace [{tmpdir}]? [y/N]: ").strip().lower()
    if keep in ("y", "yes"):
        print(f"  Kept: {tmpdir}")
    else:
        shutil.rmtree(tmpdir)
        print("  Cleaned up.")

    print("\nDone.")


if __name__ == "__main__":
    main()
