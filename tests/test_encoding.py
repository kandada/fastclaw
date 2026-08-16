# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""
针对 Windows 中文系统 gbk 编码导致的 UnicodeDecodeError 的回归测试。

问题：Path.read_text() / write_text() 不传 encoding 时默认使用系统 locale 编码，
在 Windows 中文系统（gbk/cp936）下无法读写 UTF-8 文件，导致启动崩溃。

修复：所有 read_text() / write_text() 显式指定 encoding="utf-8"。
"""

import json
import locale
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.app import (
    load_skills,
    load_agent_personality,
    load_settings,
    load_messages_from_jsonl,
    load_session_agent_id,
    load_agent_config,
)
from core.config import SessionStore


UTF8_CHINESE_CONTENT = """## Description
飞书技能 - 支持发送消息和操作飞书云文档（创建、读取、编辑、分享等）
"""

UTF8_CHINESE_SOUL = """# 主智能体

你是一个全能助手，可以：
- 执行命令行任务
- 调用各种技能
- 管理定时任务
"""


@pytest.fixture
def tmp_workspace(tmp_path):
    """创建临时 workspace 目录结构"""
    return tmp_path


class TestReadTextWithEncoding:
    """验证 read_text() 显式指定 encoding 后，中文内容可正确读取"""

    def test_read_utf8_file_with_chinese_gbk_locale(self, tmp_path, monkeypatch):
        """在模拟 gbk locale 环境下读取 UTF-8 中文文件"""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(UTF8_CHINESE_CONTENT, encoding="utf-8")

        monkeypatch.setattr(locale, "getpreferredencoding", lambda *a, **kw: "gbk")

        content = skill_file.read_text(encoding="utf-8")
        assert "飞书技能" in content
        assert "创建、读取、编辑、分享" in content

    def test_write_and_read_roundtrip_chinese(self, tmp_path):
        """UTF-8 写 -> UTF-8 读 中文内容往返一致"""
        original = "你好世界 🌍 — Hello World with emoji"
        f = tmp_path / "test.txt"
        f.write_text(original, encoding="utf-8")
        assert f.read_text(encoding="utf-8") == original


class TestLoadSkillsEncoding:
    """验证 load_skills 能正确读取包含中文的 SKILL.md"""

    def test_load_skills_with_chinese_skill_md(self, tmp_path, monkeypatch):
        """在 skills 目录中放置含中文的 SKILL.md，load_skills 应正确解析"""
        skills_dir = tmp_path / "skills" / "bundled" / "feishu"
        skills_dir.mkdir(parents=True)
        skill_md = skills_dir / "SKILL.md"
        skill_md.write_text(UTF8_CHINESE_CONTENT, encoding="utf-8")

        monkeypatch.setattr(locale, "getpreferredencoding", lambda *a, **kw: "gbk")

        skills = load_skills(str(tmp_path / "skills"))
        assert "feishu" in skills
        assert "飞书技能" in skills["feishu"]["description"]

    def test_load_skills_multiple_skills(self, tmp_path, monkeypatch):
        """多个含中文的技能文件应全部正确加载"""
        monkeypatch.setattr(locale, "getpreferredencoding", lambda *a, **kw: "gbk")

        for name in ["feishu", "cron", "pandas"]:
            sd = tmp_path / "skills" / "bundled" / name
            sd.mkdir(parents=True)
            (sd / "SKILL.md").write_text(
                f"## Description\n技能{name}说明 - 包含中文描述\n", encoding="utf-8"
            )

        skills = load_skills(str(tmp_path / "skills"))
        assert len(skills) == 3
        for name in ["feishu", "cron", "pandas"]:
            assert name in skills
            assert f"技能{name}" in skills[name]["description"]

    def test_load_skills_empty_dir(self, tmp_path):
        """空目录不应报错"""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skills = load_skills(str(skills_dir))
        assert skills == {}

    def test_load_skills_nonexistent_dir(self, tmp_path):
        """不存在的目录应返回空 dict"""
        skills = load_skills(str(tmp_path / "nonexistent"))
        assert skills == {}


class TestLoadAgentPersonalityEncoding:
    """验证 load_agent_personality 能正确读取含中文的 SOUL.md 等文件"""

    def test_load_personality_with_chinese(self, tmp_path, monkeypatch):
        agent_dir = tmp_path / "agents" / "main_agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "SOUL.md").write_text(UTF8_CHINESE_SOUL, encoding="utf-8")
        (agent_dir / "metadata.json").write_text(
            json.dumps({"name": "main_agent", "llm": {}}, ensure_ascii=False),
            encoding="utf-8",
        )

        monkeypatch.setattr(locale, "getpreferredencoding", lambda *a, **kw: "gbk")

        app_mod = sys.modules["core.app"]
        monkeypatch.setattr(app_mod, "get_agents_dir", lambda: agent_dir.parent)

        personality = load_agent_personality("main_agent")
        assert "主智能体" in personality
        assert "全能助手" in personality


class TestLoadMessagesEncoding:
    """验证 load_messages_from_jsonl 能正确读取 UTF-8 JSONL"""

    def test_load_messages_with_chinese(self, tmp_path, monkeypatch):
        session_dir = tmp_path / "sessions" / "test_session"
        session_dir.mkdir(parents=True)
        msg = json.dumps({"role": "user", "content": "你好世界"}, ensure_ascii=False)
        (session_dir / "messages.jsonl").write_text(msg + "\n", encoding="utf-8")

        monkeypatch.setattr(locale, "getpreferredencoding", lambda *a, **kw: "gbk")

        app_mod = sys.modules["core.app"]
        monkeypatch.setattr(app_mod, "get_sessions_dir", lambda: tmp_path / "sessions")

        messages = load_messages_from_jsonl("test_session")
        assert len(messages) == 1
        assert messages[0]["content"] == "你好世界"


class TestSessionStoreEncoding:
    """验证 SessionStore 的 UTF-8 读写"""

    def test_session_store_chinese_session_name(self, tmp_path, monkeypatch):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(locale, "getpreferredencoding", lambda *a, **kw: "gbk")
        monkeypatch.setattr(
            "core.config.get_sessions_dir", lambda: sessions_dir
        )

        # 安全卫士：快照真实 sessions.json 内容，写入后比对，确认落到的是临时目录
        real_sessions = Path(__file__).parent.parent.parent / "workspace" / "data" / "sessions"
        real_json = real_sessions / "sessions.json"
        real_before = real_json.read_text(encoding="utf-8") if real_json.exists() else None

        store = SessionStore()
        test_data = {"session_1": {"name": "中文会话名", "created_at": 1234567890}}
        store.save(test_data)
        loaded = store.load()
        assert loaded == test_data

        # 真实 sessions.json 不应被本用例改写（避免与其它用例交叉污染的误判）
        if real_json.exists():
            real_after = real_json.read_text(encoding="utf-8")
            assert real_after == real_before, (
                "SAFETY: session store wrote to REAL sessions.json! "
                "Monkeypatch may have failed."
            )


class TestSettingsEncoding:
    """验证 load_settings 的 UTF-8 读写"""

    def test_load_settings_default(self, tmp_path, monkeypatch):
        """settings 文件不存在时返回默认值"""
        settings_dir = tmp_path / "settings"
        app_mod = sys.modules["core.app"]
        monkeypatch.setattr(
            app_mod, "get_settings_file", lambda: settings_dir / "settings.json"
        )
        settings = load_settings()
        assert settings["default_agent_id"] == "main_agent"


class TestLoadAgentConfigEncoding:
    """验证 load_agent_config 的 UTF-8 读取"""

    def test_load_agent_config_with_chinese_desc(self, tmp_path, monkeypatch):
        agent_dir = tmp_path / "agents" / "test_agent"
        agent_dir.mkdir(parents=True)
        metadata = {
            "name": "test_agent",
            "description": "一个测试智能体，包含中文描述",
        }
        (agent_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
        )

        monkeypatch.setattr(locale, "getpreferredencoding", lambda *a, **kw: "gbk")

        app_mod = sys.modules["core.app"]
        monkeypatch.setattr(app_mod, "get_agents_dir", lambda: agent_dir.parent)

        config = load_agent_config("test_agent")
        assert config["description"] == "一个测试智能体，包含中文描述"


class TestLoadSessionAgentIdEncoding:
    """验证 load_session_agent_id 的 UTF-8 读取"""

    def test_load_session_agent_id_with_chinese_name(self, tmp_path, monkeypatch):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)
        sessions_data = {
            "session_1": {
                "name": "会话一",
                "agent_id": "custom_agent",
            }
        }
        (sessions_dir / "sessions.json").write_text(
            json.dumps(sessions_data, ensure_ascii=False), encoding="utf-8"
        )

        settings_file = tmp_path / "settings.json"
        settings_file.write_text(
            json.dumps({"default_agent_id": "main_agent"}), encoding="utf-8"
        )

        monkeypatch.setattr(locale, "getpreferredencoding", lambda *a, **kw: "gbk")

        app_mod = sys.modules["core.app"]
        monkeypatch.setattr(app_mod, "get_sessions_dir", lambda: sessions_dir)
        monkeypatch.setattr(app_mod, "get_settings_file", lambda: settings_file)

        agent_id = load_session_agent_id("session_1")
        assert agent_id == "custom_agent"

    def test_load_session_agent_id_fallback_to_default(self, tmp_path, monkeypatch):
        """session 没有指定 agent_id 时回退到默认值"""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "sessions.json").write_text(
            json.dumps({"session_1": {}}), encoding="utf-8"
        )

        settings_file = tmp_path / "settings.json"
        settings_file.write_text(
            json.dumps({"default_agent_id": "main_agent"}), encoding="utf-8"
        )

        monkeypatch.setattr(locale, "getpreferredencoding", lambda *a, **kw: "gbk")

        app_mod = sys.modules["core.app"]
        monkeypatch.setattr(app_mod, "get_sessions_dir", lambda: sessions_dir)
        monkeypatch.setattr(app_mod, "get_settings_file", lambda: settings_file)

        agent_id = load_session_agent_id("session_1")
        assert agent_id == "main_agent"


class TestRegressionGbkStartup:
    """
    回归测试：模拟 Windows 中文系统 gbk 编码下第二次启动。
    第一次启动后 workspace 中有 UTF-8 种子文件，
    第二次启动时 load_skills() 应能正确读取这些文件而不会 UnicodeDecodeError。
    """

    def test_simulate_second_startup(self, tmp_path, monkeypatch):
        """模拟第二次启动：workspace 中已有 UTF-8 文件，gbk 环境下应不崩溃"""
        # 模拟已被第一次启动播种的 workspace
        skills_dir = tmp_path / "skills" / "bundled"
        for skill_name in ["feishu", "cron", "pandas", "playwright"]:
            sd = skills_dir / skill_name
            sd.mkdir(parents=True)
            (sd / "SKILL.md").write_text(
                f"## Description\n{skill_name}技能 - 包含中文说明\n",
                encoding="utf-8",
            )

        agents_dir = tmp_path / "agents" / "main_agent"
        agents_dir.mkdir(parents=True)
        (agents_dir / "SOUL.md").write_text(
            "# Main Agent\n系统提示词 - 中文内容\n", encoding="utf-8"
        )
        (agents_dir / "metadata.json").write_text(
            json.dumps({"name": "main_agent", "llm": {}}, ensure_ascii=False),
            encoding="utf-8",
        )

        settings_file = tmp_path / "settings.json"
        settings_file.write_text(
            json.dumps({"default_agent_id": "main_agent"}, ensure_ascii=False),
            encoding="utf-8",
        )

        # 模拟 gbk 系统编码
        monkeypatch.setattr(locale, "getpreferredencoding", lambda *a, **kw: "gbk")

        # 以下调用都不应抛出 UnicodeDecodeError
        skills = load_skills(str(tmp_path / "skills"))
        assert len(skills) == 4
        for name in ["feishu", "cron", "pandas", "playwright"]:
            assert name in skills

        app_mod = sys.modules["core.app"]
        monkeypatch.setattr(app_mod, "get_agents_dir", lambda: agents_dir.parent)
        personality = load_agent_personality("main_agent")
        assert "中文内容" in personality

        monkeypatch.setattr(app_mod, "get_settings_file", lambda: settings_file)
        settings = load_settings()
        assert settings["default_agent_id"] == "main_agent"


class TestWriteTextEncoding:
    """验证 write_text() 显式指定 UTF-8 编码"""

    def test_write_text_with_utf8_encoding(self, tmp_path):
        """write_text 指定 utf-8 后，文件内容为 UTF-8"""
        f = tmp_path / "test.json"
        data = {"key": "值", "emoji": "😊"}
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        raw = f.read_bytes()
        # UTF-8 BOM should not be present (write_text does not add BOM)
        assert not raw.startswith(b"\xef\xbb\xbf")
        loaded = json.loads(f.read_text(encoding="utf-8"))
        assert loaded == data


class TestSpecialCharacters:
    """验证特殊字符（emoji、全角符号等）在 gbk 环境下正确处理"""

    @pytest.mark.parametrize("content", [
        "🚀 启动中…",
        "「ダウンロード」",
        "\u00a0\u2014\u2018\u2019\u201c\u201d",
        "Café résumé naïve",
        "日本語テスト — テスト",
    ])
    def test_utf8_roundtrip_special_chars(self, tmp_path, content, monkeypatch):
        monkeypatch.setattr(locale, "getpreferredencoding", lambda *a, **kw: "gbk")
        f = tmp_path / "special.txt"
        f.write_text(content, encoding="utf-8")
        assert f.read_text(encoding="utf-8") == content
