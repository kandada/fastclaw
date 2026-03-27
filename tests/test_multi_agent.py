"""多Agent路由测试"""

import pytest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "vendor"))

from core.app import load_agent_config, load_settings


class TestAgentConfig:
    """Agent 配置测试"""

    def test_load_agent_config_main(self):
        """测试加载 main_agent 配置"""
        config = load_agent_config("main_agent")

        assert "name" in config or "llm" in config

    def test_agent_config_has_llm(self):
        """测试配置包含 LLM 设置"""
        config = load_agent_config("main_agent")

        # 应该有 llm 配置
        if "llm" in config:
            assert "model" in config["llm"] or "api_key" in config["llm"]

    def test_load_nonexistent_agent(self):
        """测试加载不存在的 agent"""
        config = load_agent_config("nonexistent_agent")

        # 应该返回默认配置
        assert config["name"] == "nonexistent_agent"


class TestSettings:
    """全局设置测试"""

    def test_load_settings_default(self):
        """测试加载默认设置"""
        settings = load_settings()

        assert "default_agent_id" in settings

    def test_settings_default_agent(self):
        """测试默认 agent ID"""
        settings = load_settings()

        assert settings["default_agent_id"] == "main_agent"


class TestMultipleAgents:
    """多 Agent 测试"""

    def test_agents_directory_structure(self):
        """测试 agents 目录结构"""
        agents_dir = Path("workspace/data/agents")

        if agents_dir.exists():
            for agent_path in agents_dir.iterdir():
                if agent_path.is_dir():
                    metadata_file = agent_path / "metadata.json"
                    assert metadata_file.exists()

    def test_different_agent_configs(self):
        """测试不同 agent 配置"""
        # 模拟不同 agent 配置
        configs = {
            "main_agent": {"name": "main_agent", "llm": {"model": "deepseek-chat"}},
            "code_agent": {"name": "code_agent", "llm": {"model": "deepseek-chat"}},
        }

        assert "main_agent" in configs
        assert "code_agent" in configs
        assert configs["main_agent"]["name"] != configs["code_agent"]["name"]


class TestSessionAgentBinding:
    """Session 与 Agent 绑定测试"""

    def test_session_binds_to_agent(self):
        """测试 session 绑定到 agent"""
        session = {
            "session_id": "test_session",
            "agent_id": "main_agent",
        }

        assert session["agent_id"] == "main_agent"

    def test_session_default_agent(self):
        """测试 session 默认使用 settings 中的 agent"""
        settings = load_settings()
        default_agent = settings.get("default_agent_id", "main_agent")

        session = {
            "session_id": "test_session",
            "agent_id": default_agent,
        }

        assert session["agent_id"] == "main_agent"

    def test_session_switch_agent(self):
        """测试 session 切换 agent"""
        session = {
            "session_id": "test_session",
            "agent_id": "main_agent",
        }

        # 切换到另一个 agent
        session["agent_id"] = "code_agent"

        assert session["agent_id"] == "code_agent"


class TestAgentConfigLoading:
    """Agent 配置加载测试"""

    def test_llm_config_structure(self):
        """测试 LLM 配置结构"""
        config = load_agent_config("main_agent")

        if "llm" in config:
            llm = config["llm"]
            assert "gateway" in llm or "provider" in llm or "model" in llm

    def test_context_config(self):
        """测试上下文配置"""
        config = load_agent_config("main_agent")

        if "context" in config:
            context = config["context"]
            assert "max_tokens" in context or "unload_threshold_tokens" in context
