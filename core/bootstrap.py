"""
Workspace bootstrap —— 从 pip 包内置种子初始化 workspace。

启动时调用 copy_seed_files()，按文件粒度将预置的 skills、agents、配置
复制到用户 workspace。

规则（核心安全约束）：
┌──────────────────────────────────────────────────────────────┐
│ 目标文件已存在  →  跳过，绝不覆盖                             │
│ 目标文件不存在  →  种子复制过去（含版本升级新增的 skill）      │
│ 种子没有但用户有 →  不处理（用户可能故意删了某个 agent）       │
└──────────────────────────────────────────────────────────────┘

这样确保：
  - 首次安装：种子全部文件就位 → workspace 立即可用
  - 版本升级（种子新增 skill）：新 skill 文件不存在 → 自动获得
  - 版本升级（种子修改了已有 skill）：已有文件存在 → 不覆盖，尊重用户修改
  - 用户自定义 agent/skill → 永远不受种子影响
"""

import shutil
from pathlib import Path


def _seed_dir() -> Path | None:
    """返回包内置 workspace_seed 目录路径，不存在则返回 None。"""
    seed = Path(__file__).resolve().parent.parent / "workspace_seed"
    return seed if seed.is_dir() else None


def copy_seed_files(workspace_path: Path):
    """
    从 pip 包内置种子目录按需复制 workspace 文件。

    保护策略：逐个文件检查目标是否存在，存在则跳过。
    复制策略：先写临时文件（.tmp），成功后原子 rename，防止中断残留残缺文件。

    种子内容（与 pip 包一起分发，零网络依赖）：
      skills/bundled/          7 个预置技能
      skills/user/_template    用户技能模板
      data/agents/             3 个默认 agent (api_key 均留空)
      data/settings.json       全局设置
      data/channels/           feishu + imessage 配置模板
      data/cron/tasks.json     定时任务配置
    """
    seed = _seed_dir()
    if seed is None:
        return

    copied = 0
    for src_file in seed.rglob("*"):
        if src_file.is_dir():
            continue
        rel = src_file.relative_to(seed)
        dst = workspace_path / rel
        if dst.exists():
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        _atomic_copy(src_file, dst)
        copied += 1

    if copied:
        print(f"📦 Seeded {copied} file(s) from built-in workspace")


def _atomic_copy(src: Path, dst: Path):
    """原子复制：先写入临时文件，成功后 rename 到目标。"""
    tmp = dst.with_name("." + dst.name + ".tmp")
    shutil.copy2(src, tmp)
    tmp.rename(dst)
