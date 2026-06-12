"""
Bootstrap 模块单元测试。

测试范围：
  - _seed_dir           种子目录存在性
  - copy_seed_files     文件复制 + 不覆盖保护
  - main_agent api_key  确认为空

运行方式：
    python3 -m pytest fastclaw/tests/test_bootstrap.py -v
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastclaw.core.bootstrap import _seed_dir, copy_seed_files, _atomic_copy


# ============================================================================
# _seed_dir
# ============================================================================

class TestSeedDir:
    def test_seed_dir_exists_in_dev_mode(self):
        """开发模式下种子目录应存在。"""
        seed = _seed_dir()
        assert seed is not None, "workspace_seed/ not found in package"
        assert seed.is_dir()

    def test_seed_contains_skills(self):
        seed = _seed_dir()
        assert (seed / "skills" / "bundled" / "current_time").is_dir()
        assert (seed / "skills" / "user" / "_template").is_dir()

    def test_seed_contains_all_agents(self):
        seed = _seed_dir()
        for name in ("main_agent", "deepseek-chat", "MiniMax-M2.7"):
            assert (seed / "data" / "agents" / name / "metadata.json").is_file(), \
                f"Missing: agents/{name}/metadata.json"
            assert (seed / "data" / "agents" / name / "SOUL.md").is_file(), \
                f"Missing: agents/{name}/SOUL.md"

    def test_seed_contains_data_files(self):
        seed = _seed_dir()
        assert (seed / "data" / "settings.json").is_file()
        assert (seed / "data" / "channels" / "feishu_config.json").is_file()
        assert (seed / "data" / "cron" / "tasks.json").is_file()

    def test_seed_has_no_sessions(self):
        seed = _seed_dir()
        assert not (seed / "data" / "sessions").exists()


# ============================================================================
# copy_seed_files
# ============================================================================

class TestCopySeedFiles:
    def test_copies_all_to_empty_workspace(self, tmp_path):
        """空 workspace：全部种子文件应被复制。"""
        with patch("fastclaw.core.bootstrap._seed_dir", return_value=_seed_dir()):
            copy_seed_files(tmp_path)

        assert (tmp_path / "skills" / "bundled" / "current_time" / "main.py").exists()
        assert (tmp_path / "skills" / "user" / "_template" / "main.py").exists()
        assert (tmp_path / "data" / "agents" / "main_agent" / "metadata.json").exists()
        assert (tmp_path / "data" / "agents" / "deepseek-chat" / "metadata.json").exists()
        assert (tmp_path / "data" / "agents" / "MiniMax-M2.7" / "metadata.json").exists()
        assert (tmp_path / "data" / "settings.json").exists()
        assert (tmp_path / "data" / "channels" / "feishu_config.json").exists()
        assert (tmp_path / "data" / "cron" / "tasks.json").exists()

    def test_does_not_overwrite_existing_files(self, tmp_path):
        """已有文件绝不被种子覆盖。"""
        bundled = tmp_path / "skills" / "bundled" / "current_time"
        bundled.mkdir(parents=True)
        original = bundled / "SKILL.md"
        original.write_text("user-modified-content")

        agents = tmp_path / "data" / "agents" / "main_agent"
        agents.mkdir(parents=True)
        original_meta = agents / "metadata.json"
        original_meta.write_text('{"user_custom": true}')

        with patch("fastclaw.core.bootstrap._seed_dir", return_value=_seed_dir()):
            copy_seed_files(tmp_path)

        assert original.read_text() == "user-modified-content"
        assert original_meta.read_text() == '{"user_custom": true}'

    def test_all_agent_api_keys_are_empty(self, tmp_path):
        """所有种子 agent 的 api_key 应为空字符串，防止密钥泄露。"""
        with patch("fastclaw.core.bootstrap._seed_dir", return_value=_seed_dir()):
            copy_seed_files(tmp_path)

        for agent_name in ("main_agent", "deepseek-chat", "MiniMax-M2.7"):
            meta = json.loads(
                (tmp_path / "data" / "agents" / agent_name / "metadata.json").read_text()
            )
            assert meta["llm"]["api_key"] == "", \
                f"{agent_name} has non-empty api_key!"

    def test_skips_when_seed_not_found(self, tmp_path):
        """种子目录不存在时静默跳过，不报错。"""
        with patch("fastclaw.core.bootstrap._seed_dir", return_value=None):
            copy_seed_files(tmp_path)
        assert not any(tmp_path.iterdir())

    def test_second_run_no_new_files(self, tmp_path):
        """已完全初始化的 workspace，二次运行不产生新文件。"""
        with patch("fastclaw.core.bootstrap._seed_dir", return_value=_seed_dir()):
            copy_seed_files(tmp_path)

        before = sorted(f.relative_to(tmp_path) for f in tmp_path.rglob("*") if f.is_file())

        with patch("fastclaw.core.bootstrap._seed_dir", return_value=_seed_dir()):
            copy_seed_files(tmp_path)

        after = sorted(f.relative_to(tmp_path) for f in tmp_path.rglob("*") if f.is_file())
        assert before == after

    def test_partial_workspace_fills_gaps(self, tmp_path):
        """部分初始化的 workspace，只补充缺失文件，不覆盖已有。"""
        (tmp_path / "skills" / "bundled" / "current_time").mkdir(parents=True)
        existing = tmp_path / "skills" / "bundled" / "current_time" / "main.py"
        existing.write_text("my custom skill")

        # agent 完全缺失
        assert not (tmp_path / "data" / "agents").exists()

        with patch("fastclaw.core.bootstrap._seed_dir", return_value=_seed_dir()):
            copy_seed_files(tmp_path)

        # 已有文件不变
        assert existing.read_text() == "my custom skill"
        # 缺失的 agent 被补充
        assert (tmp_path / "data" / "agents" / "main_agent" / "metadata.json").exists()
        # 缺失的技能文件被补充
        assert (tmp_path / "skills" / "bundled" / "current_time" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "bundled" / "feishu").exists()


# ============================================================================
# 版本升级场景：种子新增 skill
# ============================================================================

class TestVersionUpgrade:
    """模拟 pip 升级后种子有新增 skill 的行为。"""

    def test_new_skill_added_on_upgrade(self, tmp_path):
        """旧版 workspace 已有部分 skill，升级后新 skill 应被加入。"""
        # 先模拟旧版种子（只有 current_time, feishu）
        old_seed = tmp_path / "old_seed"
        (old_seed / "skills" / "bundled" / "current_time").mkdir(parents=True)
        (old_seed / "skills" / "bundled" / "current_time" / "main.py").write_text("old")
        (old_seed / "skills" / "bundled" / "feishu").mkdir(parents=True)
        (old_seed / "skills" / "bundled" / "feishu" / "main.py").write_text("old")
        # 注意：没有 pandas skill

        with patch("fastclaw.core.bootstrap._seed_dir", return_value=old_seed):
            copy_seed_files(tmp_path)

        # 新版种子（增加了 pandas）
        new_seed = tmp_path / "new_seed"
        (new_seed / "skills" / "bundled" / "current_time").mkdir(parents=True)
        (new_seed / "skills" / "bundled" / "current_time" / "main.py").write_text("updated")
        (new_seed / "skills" / "bundled" / "feishu").mkdir(parents=True)
        (new_seed / "skills" / "bundled" / "feishu" / "main.py").write_text("updated")
        (new_seed / "skills" / "bundled" / "pandas").mkdir(parents=True)
        (new_seed / "skills" / "bundled" / "pandas" / "main.py").write_text("new_pandas")

        with patch("fastclaw.core.bootstrap._seed_dir", return_value=new_seed):
            copy_seed_files(tmp_path)

        # 已有 skill 的内容不应被更新
        assert (tmp_path / "skills" / "bundled" / "current_time" / "main.py").read_text() == "old"
        assert (tmp_path / "skills" / "bundled" / "feishu" / "main.py").read_text() == "old"
        # 新增的 pandas skill 应被加入
        assert (tmp_path / "skills" / "bundled" / "pandas" / "main.py").read_text() == "new_pandas"

    def test_existing_skill_content_never_overwritten(self, tmp_path):
        """重点验证：已有 skill 文件内容绝对不会被种子覆盖。"""
        # 用户安装了 v1，得到 current_time skill
        with patch("fastclaw.core.bootstrap._seed_dir", return_value=_seed_dir()):
            copy_seed_files(tmp_path)

        # 用户修改了 current_time/main.py
        user_modified = tmp_path / "skills" / "bundled" / "current_time" / "main.py"
        user_modified.write_text("# MY CUSTOM CODE\nprint('hello')")
        user_mtime = user_modified.stat().st_mtime

        # 模拟重新启动（或 pip 升级），种子可能更新了这个文件
        with patch("fastclaw.core.bootstrap._seed_dir", return_value=_seed_dir()):
            copy_seed_files(tmp_path)

        # 必须保持用户版本
        assert user_modified.read_text() == "# MY CUSTOM CODE\nprint('hello')"
        assert user_modified.stat().st_mtime == user_mtime


# ============================================================================
# _atomic_copy
# ============================================================================

class TestAtomicCopy:
    def test_copies_file_content(self, tmp_path):
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("hello world")
        _atomic_copy(src, dst)
        assert dst.exists()
        assert dst.read_text() == "hello world"
        assert not list(tmp_path.glob(".*.tmp"))

    def test_no_temp_leftover(self, tmp_path):
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("data")
        _atomic_copy(src, dst)
        assert not list(tmp_path.glob(".*.tmp"))
