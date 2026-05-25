"""Workspace bootstrap module

On first start, if workspace directories are empty, download default data
(skills, agents) from GitHub. File-level check: never overwrite existing files.
"""

import sys
from pathlib import Path

import httpx


def _get_git_ref() -> str:
    try:
        from importlib.metadata import version, PackageNotFoundError
        try:
            ver = version("fastclaw-ai")
            return f"v{ver}"
        except PackageNotFoundError:
            return "main"
    except ImportError:
        return "main"


def _needs_sync(skills_dir: Path, subdir: str) -> bool:
    target = skills_dir / subdir
    if not target.exists():
        return True
    try:
        next(target.iterdir())
        return False
    except StopIteration:
        return True


def _fetch_tree(git_ref: str, prefix: str, timeout: int = 20):
    url = (
        f"https://api.github.com/repos/kandada/fastclaw/git/trees/"
        f"{git_ref}?recursive=1"
    )
    headers = {"Accept": "application/vnd.github+json"}
    try:
        resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        if resp.status_code == 404:
            if git_ref == "main":
                print("  ⚠️  GitHub tree not found (404) for main branch")
                return None, None
            return _fetch_tree("main", prefix, timeout)
        resp.raise_for_status()
        data = resp.json()
        tree = data.get("tree", [])
        items = [
            item
            for item in tree
            if item["type"] == "blob" and item["path"].startswith(prefix)
        ]
        return items, git_ref
    except Exception as e:
        print(f"  ⚠️  Failed to fetch file list for '{prefix}': {e}")
        return None, None


def _fetch_skills_tree(git_ref: str, timeout: int = 20):
    return _fetch_tree(git_ref, "workspace/skills/", timeout)


def _download_file(url: str, local_path: Path, timeout: int = 20) -> bool:
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"\n  ⚠️  Download failed: {local_path.name} - {e}")
        return False


def _sync_subdir(tree_files: list, git_ref: str, sub: str, skills_dir: Path):
    prefix = f"workspace/skills/{sub}/"
    sub_files = [item for item in tree_files if item["path"].startswith(prefix)]

    if not sub_files:
        print(f"  No files found for '{sub}' on GitHub, skipped")
        return

    target_dir = skills_dir / sub
    target_dir.mkdir(parents=True, exist_ok=True)

    total = len(sub_files)
    success = 0

    print(f"  [{sub}/] {total} files:")

    for i, item in enumerate(sub_files):
        rel_path = item["path"][len("workspace/skills/"):]
        local_path = skills_dir / rel_path

        if local_path.exists():
            success += 1
            continue

        raw_url = (
            f"https://raw.githubusercontent.com/kandada/fastclaw/"
            f"{git_ref}/{item['path']}"
        )

        bar_len = 24
        n = i + 1
        filled = int(bar_len * n / total)
        bar = "█" * filled + "░" * (bar_len - filled)

        sys.stdout.write(f"\r    [{bar}] {n}/{total}  {rel_path}")
        sys.stdout.flush()

        if _download_file(raw_url, local_path):
            success += 1

    print()
    if success < total:
        print(f"  ⚠️  Partial ({success}/{total} succeeded, {total - success} failed)")
    else:
        print(f"  ✅ Done ({success} files)")


def sync_skills_if_missing(workspace_path: Path):
    skills_dir = workspace_path / "skills"

    subdirs_to_sync = []
    for sub in ("bundled", "user"):
        if _needs_sync(skills_dir, sub):
            subdirs_to_sync.append(sub)

    if not subdirs_to_sync:
        return

    print("\n📥 Skills directory is empty, downloading from GitHub...")

    git_ref = _get_git_ref()
    print(f"   Ref: {git_ref}")

    tree_files, effective_ref = _fetch_skills_tree(git_ref)
    if tree_files is None:
        print("  ⚠️  Download failed, skipped (normal startup unaffected)\n")
        return

    if effective_ref != git_ref:
        print(f"   (using branch: {effective_ref})")

    for sub in subdirs_to_sync:
        _sync_subdir(tree_files, effective_ref, sub, skills_dir)

    print()


def _needs_agent_sync(agents_dir: Path) -> bool:
    if not agents_dir.exists():
        return True
    try:
        next(agents_dir.iterdir())
        return False
    except StopIteration:
        return True


def _sync_agents(tree_files: list, git_ref: str, agents_dir: Path):
    prefix = "workspace/data/agents/"
    agent_items = [item for item in tree_files if item["path"].startswith(prefix)]

    if not agent_items:
        print("  No default agents found on GitHub, skipped")
        return

    agent_dirs: dict[str, list] = {}
    for item in agent_items:
        rel = item["path"][len(prefix):]
        parts = rel.split("/", 1)
        if len(parts) < 2:
            continue
        agent_name = parts[0]
        agent_dirs.setdefault(agent_name, []).append(item)

    total_agents = len(agent_dirs)
    synced = 0

    print(f"  [{total_agents} agent(s) found]")

    for agent_name, items in sorted(agent_dirs.items()):
        target_dir = agents_dir / agent_name
        if target_dir.exists():
            synced += 1
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        agent_success = 0

        for item in items:
            rel = item["path"][len(prefix):]
            local_path = agents_dir / rel

            raw_url = (
                f"https://raw.githubusercontent.com/kandada/fastclaw/"
                f"{git_ref}/{item['path']}"
            )
            if _download_file(raw_url, local_path):
                agent_success += 1

        status = "✅" if agent_success == len(items) else "⚠️"
        print(f"    {status} {agent_name}/ ({agent_success}/{len(items)} files)")
        synced += 1

    if synced < total_agents:
        print(f"  ⚠️  Partial sync: {synced}/{total_agents} agents")


def sync_agents_if_missing(workspace_path: Path):
    agents_dir = workspace_path / "data" / "agents"

    if not _needs_agent_sync(agents_dir):
        return

    print("\n📥 Agents directory is empty, downloading defaults from GitHub...")

    git_ref = _get_git_ref()
    print(f"   Ref: {git_ref}")

    tree_files, effective_ref = _fetch_tree(git_ref, "workspace/data/agents/")
    if tree_files is None:
        print("  ⚠️  Download failed, skipped (normal startup unaffected)\n")
        return

    if effective_ref != git_ref:
        print(f"   (using branch: {effective_ref})")

    _sync_agents(tree_files, effective_ref, agents_dir)
    print()
