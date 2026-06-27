# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""core/config.py 配置模块测试"""

import json
from pathlib import Path

from core.config import (
    get_workspace_path,
    ensure_workspace,
    get_data_dir,
    get_sessions_dir,
    get_agents_dir,
    get_channels_dir,
    get_cron_dir,
    get_skills_dir,
    get_settings_file,
    ensure_settings,
)


class TestGetWorkspacePath:
    """get_workspace_path 路径优先级测试"""

    def test_env_var_highest_priority(self, monkeypatch):
        tmp = Path("/tmp/fastclaw_test_env")
        monkeypatch.setenv("FASTCLAW_WORKSPACE", str(tmp))
        get_workspace_path.cache_clear()
        result = get_workspace_path()
        assert result == tmp.resolve()

    def test_env_var_resolves_relative(self, monkeypatch, tmp_path):
        p = tmp_path / "env_ws"
        monkeypatch.setenv("FASTCLAW_WORKSPACE", str(p))
        get_workspace_path.cache_clear()
        result = get_workspace_path()
        assert result == p.resolve()

    def test_env_var_overrides_all(self, monkeypatch, tmp_path):
        """env var 优先级最高，即使包目录 workspace 存在"""
        current = get_workspace_path()
        p = tmp_path / "env_override"
        monkeypatch.setenv("FASTCLAW_WORKSPACE", str(p))
        get_workspace_path.cache_clear()
        result = get_workspace_path()
        assert result == p.resolve()
        assert result != current


class TestEnsureWorkspace:
    """ensure_workspace 目录结构创建"""

    def test_creates_directory_structure(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FASTCLAW_WORKSPACE", str(tmp_path / "ws"))
        get_workspace_path.cache_clear()

        result = ensure_workspace()

        assert result == (tmp_path / "ws").resolve()
        assert (tmp_path / "ws" / "data" / "agents").is_dir()
        assert (tmp_path / "ws" / "data" / "sessions").is_dir()
        assert (tmp_path / "ws" / "skills" / "bundled").is_dir()
        assert (tmp_path / "ws" / "skills" / "user").is_dir()

    def test_second_call_is_idempotent(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FASTCLAW_WORKSPACE", str(tmp_path / "ws2"))
        get_workspace_path.cache_clear()
        ensure_workspace()
        ensure_workspace()


class TestDirGetters:
    """子目录路径获取"""

    def test_get_data_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FASTCLAW_WORKSPACE", str(tmp_path / "ws"))
        get_workspace_path.cache_clear()
        assert get_data_dir() == (tmp_path / "ws" / "data").resolve()

    def test_get_sessions_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FASTCLAW_WORKSPACE", str(tmp_path / "ws"))
        get_workspace_path.cache_clear()
        assert get_sessions_dir() == (tmp_path / "ws" / "data" / "sessions").resolve()

    def test_get_agents_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FASTCLAW_WORKSPACE", str(tmp_path / "ws"))
        get_workspace_path.cache_clear()
        assert get_agents_dir() == (tmp_path / "ws" / "data" / "agents").resolve()

    def test_get_channels_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FASTCLAW_WORKSPACE", str(tmp_path / "ws"))
        get_workspace_path.cache_clear()
        assert get_channels_dir() == (tmp_path / "ws" / "data" / "channels").resolve()

    def test_get_cron_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FASTCLAW_WORKSPACE", str(tmp_path / "ws"))
        get_workspace_path.cache_clear()
        assert get_cron_dir() == (tmp_path / "ws" / "data" / "cron").resolve()

    def test_get_skills_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FASTCLAW_WORKSPACE", str(tmp_path / "ws"))
        get_workspace_path.cache_clear()
        assert get_skills_dir() == (tmp_path / "ws" / "skills").resolve()

    def test_get_settings_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FASTCLAW_WORKSPACE", str(tmp_path / "ws"))
        get_workspace_path.cache_clear()
        assert get_settings_file() == (tmp_path / "ws" / "data" / "settings.json").resolve()


class TestEnsureSettings:
    """ensure_settings 测试"""

    def test_creates_default_settings_when_missing(self, monkeypatch, tmp_path):
        ws = tmp_path / "test_settings_ws"
        monkeypatch.setenv("FASTCLAW_WORKSPACE", str(ws))
        get_workspace_path.cache_clear()
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "data").mkdir(parents=True, exist_ok=True)

        ensure_settings()

        sf = ws / "data" / "settings.json"
        assert sf.exists()
        data = json.loads(sf.read_text())
        assert data["default_agent_id"] == "main_agent"
        assert data["run_shell_timeout"] == 60

    def test_does_not_overwrite_existing_settings(self, monkeypatch, tmp_path):
        ws = tmp_path / "test_settings_existing"
        monkeypatch.setenv("FASTCLAW_WORKSPACE", str(ws))
        get_workspace_path.cache_clear()
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "data").mkdir(parents=True, exist_ok=True)

        custom = {"default_agent_id": "custom_agent", "run_shell_timeout": 120}
        (ws / "data" / "settings.json").write_text(json.dumps(custom))

        ensure_settings()

        data = json.loads((ws / "data" / "settings.json").read_text())
        assert data["default_agent_id"] == "custom_agent"
        assert data["run_shell_timeout"] == 120
