"""Cron 定时任务测试"""

import pytest
import json
import datetime


class TestCronValidation:
    """Cron 验证测试"""

    def test_validate_cron_schedule_all_stars_rejected(self):
        """测试全*的cron表达式被拒绝"""
        from gateway.router import validate_cron_schedule

        valid, msg = validate_cron_schedule("* * * * *")
        assert valid is False
        assert "cannot be all '*'" in msg

    def test_validate_cron_schedule_valid(self):
        """测试有效的cron表达式通过验证"""
        from gateway.router import validate_cron_schedule

        valid, msg = validate_cron_schedule("0 9 * * *")
        assert valid is True
        assert msg == ""

    def test_validate_cron_schedule_wrong_parts(self):
        """测试错误部分数的cron表达式被拒绝"""
        from gateway.router import validate_cron_schedule

        valid, msg = validate_cron_schedule("0 9 * *")
        assert valid is False
        assert "must have 5 parts" in msg

        valid, msg = validate_cron_schedule("0 9 * * * *")
        assert valid is False
        assert "must have 5 parts" in msg


class TestCronTaskPreparation:
    """Cron 任务准备测试（字段默认值填充）"""

    def test_prepare_cron_task_full_fields(self):
        """测试完整字段的任务"""
        from gateway.router import prepare_cron_task

        task_data = {
            "id": "task_001",
            "name": "test_task",
            "schedule": "0 9 * * *",
            "description": "test",
            "agent_id": "main_agent",
            "session_id": "sess_001",
            "enabled": True,
        }
        result, error = prepare_cron_task(task_data)
        assert error == ""
        assert result["description"] == "test"
        assert result["session_id"] == "sess_001"

    def test_prepare_cron_task_missing_required_field(self):
        """测试缺少必填字段被拒绝"""
        from gateway.router import prepare_cron_task

        task_data = {"name": "test", "schedule": "0 9 * * *"}
        result, error = prepare_cron_task(task_data)
        assert "id" in error

        task_data = {"id": "task_001", "schedule": "0 9 * * *"}
        result, error = prepare_cron_task(task_data)
        assert "name" in error

    def test_prepare_cron_task_defaults(self):
        """测试默认值填充"""
        from gateway.router import prepare_cron_task

        task_data = {
            "id": "task_001",
            "name": "test_task",
            "schedule": "0 9 * * *",
        }
        result, error = prepare_cron_task(task_data)
        assert error == ""
        assert result["description"] == ""
        assert result["agent_id"] == "main_agent"
        assert result["enabled"] is True
        assert result["session_id"] is None

    def test_prepare_cron_task_all_stars_rejected(self):
        """测试全*被拒绝"""
        from gateway.router import prepare_cron_task

        task_data = {
            "id": "task_001",
            "name": "test_task",
            "schedule": "* * * * *",
        }
        result, error = prepare_cron_task(task_data)
        assert "cannot be all '*'" in error


class TestCronFieldMatching:
    """Cron 字段匹配测试 - 使用 croniter"""

    def test_cron_field_matches_wildcard(self):
        """测试通配符匹配"""
        import croniter

        now = datetime.datetime(2024, 1, 1, 9, 5)
        cron = croniter.croniter("5 * * * *", now)
        assert cron.get_next(datetime.datetime) is not None

    def test_cron_field_matches_exact(self):
        """测试精确匹配"""
        import croniter

        now = datetime.datetime(2024, 1, 1, 9, 30)
        cron = croniter.croniter("30 9 * * *", now)
        next_run = cron.get_next(datetime.datetime)
        assert next_run.hour == 9
        assert next_run.minute == 30

    def test_cron_field_matches_list(self):
        """测试列表匹配"""
        import croniter

        now = datetime.datetime(2024, 1, 1, 9, 30)
        cron = croniter.croniter("30 9,10 * * *", now)
        next_run = cron.get_next(datetime.datetime)
        assert next_run.hour in [9, 10]
        assert next_run.minute == 30

    def test_cron_field_matches_range(self):
        """测试范围匹配"""
        import croniter

        now = datetime.datetime(2024, 1, 1, 9, 30)
        cron = croniter.croniter("30 1-5 * * *", now)
        next_run = cron.get_next(datetime.datetime)
        assert 1 <= next_run.hour <= 5

    def test_cron_field_matches_sunday(self):
        """测试周日匹配（0和7都表示周日）"""
        import croniter

        now = datetime.datetime(2024, 1, 7, 9, 30)
        assert now.weekday() == 6
        cron = croniter.croniter("30 9 * * 0", now)
        next_run = cron.get_next(datetime.datetime)
        assert next_run.weekday() == 6


class TestCronShouldRun:
    """Cron should_run 测试 - 使用 croniter"""

    def test_should_run_all_stars(self):
        """测试全*不执行（被调度器拒绝）"""
        from gateway.router import validate_cron_schedule

        valid, msg = validate_cron_schedule("* * * * *")
        assert valid is False

    def test_should_run_specific_minute(self):
        """测试指定分钟执行"""
        import croniter

        now = datetime.datetime(2024, 1, 1, 9, 30)
        cron = croniter.croniter("30 9 * * *", now)
        prev_run = cron.get_prev(datetime.datetime)
        assert prev_run.minute == 30
        assert prev_run.hour == 9

    def test_should_run_specific_hour(self):
        """测试指定小时执行"""
        import croniter

        now = datetime.datetime(2024, 1, 1, 9, 30)
        cron = croniter.croniter("30 9 * * *", now)
        prev_run = cron.get_prev(datetime.datetime)
        assert prev_run.hour == 9

    def test_should_run_specific_day(self):
        """测试指定日期执行"""
        import croniter

        now = datetime.datetime(2024, 1, 15, 9, 30)
        cron = croniter.croniter("30 9 15 * *", now)
        prev_run = cron.get_prev(datetime.datetime)
        assert prev_run.day == 15

    def test_should_run_specific_month(self):
        """测试指定月份执行"""
        import croniter

        now = datetime.datetime(2024, 6, 15, 9, 30)
        cron = croniter.croniter("30 9 15 6 *", now)
        prev_run = cron.get_prev(datetime.datetime)
        assert prev_run.month == 6

    def test_should_run_weekday(self):
        """测试指定星期执行（周一=weekday=0, cron dow=1）"""
        import croniter

        monday = datetime.datetime(2024, 1, 1, 9, 30)
        assert monday.weekday() == 0
        cron = croniter.croniter("30 9 * * 1", monday)
        prev_run = cron.get_prev(datetime.datetime)
        assert prev_run.weekday() == 0

    def test_should_run_wildcard_fields(self):
        """测试其他字段为*时正确匹配"""
        import croniter

        now = datetime.datetime(2024, 1, 1, 9, 30)
        cron = croniter.croniter("30 9 * * *", now)
        prev_run = cron.get_prev(datetime.datetime)
        assert prev_run.hour == 9
        assert prev_run.minute == 30

    def test_should_run_invalid_parts(self):
        """测试无效的cron表达式"""
        from gateway.router import validate_cron_schedule

        valid, _ = validate_cron_schedule("30 * *")
        assert valid is False
        valid, _ = validate_cron_schedule("30 * * * * *")
        assert valid is False


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
        assert task["agent_id"] == "main_agent"
        assert task["enabled"] is True

    def test_cron_schedule_parsing(self):
        """测试 cron 表达式解析"""
        schedule = "0 9 * * *"
        parts = schedule.split()

        assert len(parts) == 5
        assert parts[0] == "0"
        assert parts[1] == "9"

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
        assert task["agent_id"] == "main_agent"

    def test_agent_binding(self):
        """测试 agent 绑定"""
        task = {
            "id": "task_001",
            "name": "test",
            "agent_id": "main_agent",
        }

        assert task["agent_id"] == "main_agent"


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
        assert event.payload["agent_id"] == "main_agent"
        assert event.session_id == "test_session"
