"""Cron 定时任务测试"""

import pytest
import json
import datetime
from pathlib import Path


class TestCronTaskFormat:
    """Cron 任务格式测试"""

    def test_cron_task_structure(self):
        """测试 cron 任务结构"""
        task = {
            "id": "task_001",
            "name": "daily_report",
            "schedule": "0 9 * * *",
            "description": "生成并发送每日报告",
            "agent_id": "main_agent",
            "session_id": "abc123",
            "enabled": True,
        }

        assert task["id"] == "task_001"
        assert task["name"] == "daily_report"
        assert task["enabled"] is True

    def test_cron_schedule_parsing(self):
        """测试 cron 表达式解析"""
        schedule = "0 9 * * *"
        parts = schedule.split()

        assert len(parts) == 5
        assert parts[0] == "0"  # minute
        assert parts[1] == "9"  # hour

    def test_should_run_every_minute(self):
        """测试每分钟执行"""
        schedule = "* * * * *"
        parts = schedule.split()
        minute = parts[0]

        assert minute == "*"

    def test_should_run_specific_minute(self):
        """测试指定分钟执行"""

        def should_run(now, schedule):
            parts = schedule.split()
            if len(parts) != 5:
                return False
            minute = parts[0]
            if minute == "*":
                return True
            if now.minute == int(minute):
                return True
            return False

        now = datetime.datetime(2024, 1, 1, 9, 30)
        assert should_run(now, "* * * * *") is True
        assert should_run(now, "30 * * * *") is True
        assert should_run(now, "0 * * * *") is False


class TestCronTaskStorage:
    """Cron 任务存储测试"""

    def test_save_and_load_cron_tasks(self, tmp_path):
        """测试保存和加载 cron 任务"""
        tasks_file = tmp_path / "tasks.json"

        tasks = [
            {
                "id": "task_001",
                "name": "test_task",
                "schedule": "0 9 * * *",
                "enabled": True,
            }
        ]

        tasks_file.write_text(json.dumps(tasks))

        loaded = json.loads(tasks_file.read_text())
        assert len(loaded) == 1
        assert loaded[0]["id"] == "task_001"

    def test_cron_tasks_disabled(self, tmp_path):
        """测试禁用的任务不执行"""
        tasks_file = tmp_path / "tasks.json"

        tasks = [
            {
                "id": "task_001",
                "name": "disabled_task",
                "schedule": "* * * * *",
                "enabled": False,
            }
        ]

        tasks_file.write_text(json.dumps(tasks))
        loaded = json.loads(tasks_file.read_text())

        assert loaded[0]["enabled"] is False


class TestCronTaskExecution:
    """Cron 任务执行测试"""

    def test_session_binding(self):
        """测试 session 绑定"""
        task = {
            "id": "task_001",
            "name": "test",
            "session_id": "my_session",
            "agent_id": "main_agent",
        }

        assert task["session_id"] == "my_session"

    def test_agent_binding(self):
        """测试 agent 绑定"""
        task = {
            "id": "task_001",
            "name": "test",
            "agent_id": "code_agent",
        }

        assert task["agent_id"] == "code_agent"


class TestCronEventGeneration:
    """Cron 事件生成测试"""

    def test_cron_triggered_event_format(self):
        """测试 cron.triggered 事件格式"""
        from fastmind import Event

        event = Event(
            type="cron.triggered",
            payload={
                "task_id": "task_001",
                "task_name": "daily_report",
                "description": "生成并发送每日报告",
                "agent_id": "main_agent",
            },
            session_id="test_session",
        )

        assert event.type == "cron.triggered"
        assert event.payload["task_id"] == "task_001"
        assert event.session_id == "test_session"
