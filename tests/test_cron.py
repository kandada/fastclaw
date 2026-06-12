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


# ============================================================
# Scheduler trigger logic tests (测试 _check_and_trigger 核心逻辑)
# ============================================================


def _make_task(task_id="t1", schedule="30 * * * *", enabled=True,
               last_triggered=None, session_id="default"):
    """Helper to create a CronTask for testing."""
    from gateway.cron_scheduler import CronTask, CronScheduler
    return CronTask(
        id=task_id,
        name=f"task_{task_id}",
        schedule=schedule,
        description="test",
        agent_id="main_agent",
        session_id=session_id,
        enabled=enabled,
        last_triggered=last_triggered,
    )


def _make_scheduler(tasks=None, max_missed_seconds=300):
    """Helper to create a CronScheduler with given tasks."""
    from gateway.cron_scheduler import CronScheduler
    sched = CronScheduler(max_missed_seconds=max_missed_seconds)
    if tasks:
        for t in tasks:
            sched._tasks[t.id] = t
    return sched


async def _run_check(scheduler, now_dt):
    """Run _check_and_trigger at a fake 'now', return set of triggered task_ids."""
    triggered = set()

    async def fake_enqueue(task):
        triggered.add(task.id)

    original_enqueue = scheduler._enqueue_message
    scheduler._enqueue_message = fake_enqueue

    await scheduler._check_and_trigger(_now=now_dt)

    scheduler._enqueue_message = original_enqueue
    return triggered


class TestCheckAndTrigger:
    """测试 _check_and_trigger 调度核心逻辑"""

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_triggers_when_now_is_after_schedule(self):
        """now=10:31, schedule='30 * * * *' → 应触发 10:30 这次"""
        now = datetime.datetime(2024, 1, 1, 10, 31, 0)
        task = _make_task("t1", schedule="30 * * * *")
        scheduler = _make_scheduler([task])

        triggered = await _run_check(scheduler, now)
        assert "t1" in triggered
        assert task.last_triggered == datetime.datetime(2024, 1, 1, 10, 30)

    @pytest.mark.asyncio
    async def test_does_not_trigger_before_schedule(self):
        """now=10:29, schedule='30 * * * *' → 不应触发，还没到 10:30"""
        now = datetime.datetime(2024, 1, 1, 10, 29, 0)
        task = _make_task("t1", schedule="30 * * * *")
        scheduler = _make_scheduler([task])

        triggered = await _run_check(scheduler, now)
        assert "t1" not in triggered
        assert task.last_triggered is None

    @pytest.mark.asyncio
    async def test_skips_already_triggered_time(self):
        """last_triggered=10:30, now=10:31 → 不应重复触发 10:30"""
        now = datetime.datetime(2024, 1, 1, 10, 31, 0)
        last = datetime.datetime(2024, 1, 1, 10, 30)
        task = _make_task("t1", schedule="30 * * * *", last_triggered=last)
        scheduler = _make_scheduler([task])

        triggered = await _run_check(scheduler, now)
        assert "t1" not in triggered
        assert task.last_triggered == last

    @pytest.mark.asyncio
    async def test_triggers_next_after_last_triggered(self):
        """last_triggered=10:30, now=11:31 → 应触发 11:30 (下一小时的)"""
        now = datetime.datetime(2024, 1, 1, 11, 31, 0)
        last = datetime.datetime(2024, 1, 1, 10, 30)
        task = _make_task("t1", schedule="30 * * * *", last_triggered=last)
        scheduler = _make_scheduler([task])

        triggered = await _run_check(scheduler, now)
        assert "t1" in triggered
        assert task.last_triggered == datetime.datetime(2024, 1, 1, 11, 30)

    @pytest.mark.asyncio
    async def test_triggers_multiple_missed_within_window(self):
        """last_triggered=None, now=11:35, schedule='30 * * * *' →
        应触发 10:30 和 11:30 (missed_seconds=330 和 30，第一个跳过第二个触发)"""
        now = datetime.datetime(2024, 1, 1, 11, 35, 0)
        task = _make_task("t1", schedule="30 * * * *")
        scheduler = _make_scheduler([task], max_missed_seconds=600)

        triggered = await _run_check(scheduler, now)
        assert "t1" in triggered
        assert task.last_triggered == datetime.datetime(2024, 1, 1, 11, 30)

    @pytest.mark.asyncio
    async def test_skips_far_missed_first_run(self):
        """last_triggered=None (首次), now 远超 schedule → 不应触发过去的"""
        now = datetime.datetime(2024, 1, 1, 12, 0, 0)
        task = _make_task("t1", schedule="30 * * * *")
        scheduler = _make_scheduler([task], max_missed_seconds=300)

        triggered = await _run_check(scheduler, now)
        assert "t1" not in triggered
        assert task.last_triggered is None

    @pytest.mark.asyncio
    async def test_disabled_task_not_triggered(self):
        """禁用的任务不应触发"""
        now = datetime.datetime(2024, 1, 1, 10, 31, 0)
        task = _make_task("t1", schedule="30 * * * *", enabled=False)
        scheduler = _make_scheduler([task])

        triggered = await _run_check(scheduler, now)
        assert "t1" not in triggered

    @pytest.mark.asyncio
    async def test_every_5_minutes(self):
        """schedule='*/5 * * * *', now=10:36 → 应触发 10:35"""
        now = datetime.datetime(2024, 1, 1, 10, 36, 0)
        task = _make_task("t1", schedule="*/5 * * * *")
        scheduler = _make_scheduler([task])

        triggered = await _run_check(scheduler, now)
        assert "t1" in triggered
        assert task.last_triggered == datetime.datetime(2024, 1, 1, 10, 35)

    @pytest.mark.asyncio
    async def test_every_5_minutes_not_trigger_before(self):
        """schedule='*/5 * * * *', now=10:34, max_missed=60 → seed=10:33,
        get_next=10:35 > 10:34 → 不应触发（10:30 已超出 60s 窗口）"""
        now = datetime.datetime(2024, 1, 1, 10, 34, 0)
        task = _make_task("t1", schedule="*/5 * * * *")
        scheduler = _make_scheduler([task], max_missed_seconds=60)

        triggered = await _run_check(scheduler, now)
        assert "t1" not in triggered

    @pytest.mark.asyncio
    async def test_specific_hour_and_minute(self):
        """schedule='0 9 * * *', now=9:01 → 应触发 9:00"""
        now = datetime.datetime(2024, 1, 1, 9, 1, 0)
        task = _make_task("t1", schedule="0 9 * * *")
        scheduler = _make_scheduler([task])

        triggered = await _run_check(scheduler, now)
        assert "t1" in triggered
        assert task.last_triggered == datetime.datetime(2024, 1, 1, 9, 0)

    @pytest.mark.asyncio
    async def test_specific_hour_not_trigger_other_hour(self):
        """schedule='0 9 * * *', now=10:01 → 10:00 不应触发（cron 只匹配 9:00）"""
        now = datetime.datetime(2024, 1, 1, 10, 1, 0)
        task = _make_task("t1", schedule="0 9 * * *")
        scheduler = _make_scheduler([task])

        triggered = await _run_check(scheduler, now)
        assert "t1" not in triggered

    @pytest.mark.asyncio
    async def test_weekday_only_triggers_on_weekday(self):
        """schedule='30 9 * * 1-5', 周一 9:31 → 应触发"""
        import datetime as dt
        now = dt.datetime(2024, 1, 1, 9, 31, 0)  # 2024-01-01 is Monday
        assert now.weekday() == 0
        task = _make_task("t1", schedule="30 9 * * 1-5")
        scheduler = _make_scheduler([task])

        triggered = await _run_check(scheduler, now)
        assert "t1" in triggered
        assert task.last_triggered == dt.datetime(2024, 1, 1, 9, 30)

    @pytest.mark.asyncio
    async def test_weekday_skips_weekend(self):
        """schedule='30 9 * * 1-5', 周日 9:31 → 不应触发"""
        import datetime as dt
        now = dt.datetime(2024, 1, 7, 9, 31, 0)  # 2024-01-07 is Sunday
        assert now.weekday() == 6
        task = _make_task("t1", schedule="30 9 * * 1-5")
        scheduler = _make_scheduler([task])

        triggered = await _run_check(scheduler, now)
        assert "t1" not in triggered

    @pytest.mark.asyncio
    async def test_first_run_triggers_within_window(self):
        """首次运行，now=10:31, schedule='30 * * * *', max_missed=120 →
        应触发 10:30（在 120s 窗口内）"""
        now = datetime.datetime(2024, 1, 1, 10, 31, 0)
        task = _make_task("t1", schedule="30 * * * *")
        scheduler = _make_scheduler([task], max_missed_seconds=120)

        triggered = await _run_check(scheduler, now)
        assert "t1" in triggered
        assert task.last_triggered == datetime.datetime(2024, 1, 1, 10, 30)

    @pytest.mark.asyncio
    async def test_first_run_skips_tight_window(self):
        """首次运行，now=10:31, schedule='30 * * * *', max_missed=30 →
        seed=10:30:29, get_next=10:30? 不管 get_next 返回啥，missed > 30 → 跳过"""
        now = datetime.datetime(2024, 1, 1, 10, 31, 0)
        task = _make_task("t1", schedule="30 * * * *")
        scheduler = _make_scheduler([task], max_missed_seconds=30)

        triggered = await _run_check(scheduler, now)
        assert "t1" not in triggered
        assert task.last_triggered is None

    @pytest.mark.asyncio
    async def test_first_run_skips_far_past(self):
        """首次运行，now=12:00, schedule='30 * * * *', max_missed=300 →
        seed=11:55, get_next=12:30 > 12:00 → 不触发（下一个未来的触发点还没到）"""
        now = datetime.datetime(2024, 1, 1, 12, 0, 0)
        task = _make_task("t1", schedule="30 * * * *")
        scheduler = _make_scheduler([task], max_missed_seconds=300)

        triggered = await _run_check(scheduler, now)
        assert "t1" not in triggered
        assert task.last_triggered is None

    @pytest.mark.asyncio
    async def test_multiple_tasks_independent(self):
        """多个任务各自独立触发，max_missed=3600 足够覆盖 10:00 到 10:31 的窗口"""
        now = datetime.datetime(2024, 1, 1, 10, 31, 0)
        t1 = _make_task("t1", schedule="30 * * * *")
        t2 = _make_task("t2", schedule="0 10 * * *")
        scheduler = _make_scheduler([t1, t2], max_missed_seconds=3600)

        triggered = await _run_check(scheduler, now)
        assert "t1" in triggered   # 10:30
        assert "t2" in triggered   # 10:00
        assert t1.last_triggered == datetime.datetime(2024, 1, 1, 10, 30)
        assert t2.last_triggered == datetime.datetime(2024, 1, 1, 10, 0)


class TestCheckAndTriggerMidnight:
    """午夜跨天场景"""

    @pytest.mark.asyncio
    async def test_midnight_daily_task(self):
        """跨午夜，每日 0:0 任务在 0:01 触发"""
        now = datetime.datetime(2024, 1, 2, 0, 1, 0)
        task = _make_task("t1", schedule="0 0 * * *",
                          last_triggered=datetime.datetime(2024, 1, 1, 0, 0))
        scheduler = _make_scheduler([task])

        triggered = await _run_check(scheduler, now)
        assert "t1" in triggered
        assert task.last_triggered == datetime.datetime(2024, 1, 2, 0, 0)


class TestCheckAndTriggerSkipAdvancesState:
    """跳过积压事件时必须推进 last_triggered，避免每 60s 重复扫描"""

    @pytest.mark.asyncio
    async def test_skip_advances_last_triggered(self):
        """last_triggered=Jan1, max_missed=30, now=Jan3 00:01 → Jan2 和 Jan3 都被跳过，
        但 last_triggered 推进到 Jan3，不会停在 None"""
        last = datetime.datetime(2024, 1, 1, 0, 0)
        now = datetime.datetime(2024, 1, 3, 0, 1, 0)
        task = _make_task("t1", schedule="0 0 * * *", last_triggered=last)
        scheduler = _make_scheduler([task], max_missed_seconds=30)

        triggered = await _run_check(scheduler, now)
        assert "t1" not in triggered
        assert task.last_triggered is not None
        assert task.last_triggered >= datetime.datetime(2024, 1, 3, 0, 0)

    @pytest.mark.asyncio
    async def test_skip_no_rescan_on_next_cycle(self):
        """首次扫描推进了 last_triggered，60s 后再查不重复扫描跳过的事件"""
        last = datetime.datetime(2024, 1, 1, 0, 0)
        now = datetime.datetime(2024, 1, 3, 0, 1, 0)
        task = _make_task("t1", schedule="0 0 * * *", last_triggered=last)
        scheduler = _make_scheduler([task], max_missed_seconds=30)

        triggered1 = await _run_check(scheduler, now)
        assert "t1" not in triggered1
        first_lt = task.last_triggered
        assert first_lt is not None

        triggered2 = await _run_check(scheduler, now)
        assert "t1" not in triggered2
        assert task.last_triggered == first_lt

    @pytest.mark.asyncio
    async def test_skip_then_trigger_on_time(self):
        """跳过积压后，到点仍能正常触发"""
        last = datetime.datetime(2024, 1, 1, 0, 0)
        now1 = datetime.datetime(2024, 1, 3, 0, 1, 0)
        task = _make_task("t1", schedule="0 0 * * *", last_triggered=last)
        scheduler = _make_scheduler([task], max_missed_seconds=300)

        triggered1 = await _run_check(scheduler, now1)
        assert "t1" in triggered1  # Jan 3 midnight 60s 内, 在 300s 窗口内触发
        assert task.last_triggered == datetime.datetime(2024, 1, 3, 0, 0)

        now2 = datetime.datetime(2024, 1, 4, 0, 1, 0)
        triggered2 = await _run_check(scheduler, now2)
        assert "t1" in triggered2
        assert task.last_triggered == datetime.datetime(2024, 1, 4, 0, 0)


class TestSaveLoadLastTriggered:
    """持久化 last_triggered 测试"""

    def test_save_includes_last_triggered(self, tmp_path):
        from gateway.cron_scheduler import CronScheduler, CronTask
        import datetime as dt

        tasks_file = tmp_path / "tasks.json"
        sched = CronScheduler.__new__(CronScheduler)
        sched._task_file = tasks_file
        sched._tasks = {}
        sched._running = False
        sched._runner_task = None
        sched._queues = {}
        sched._processing = {}
        sched._push_callback = None
        sched._max_missed_seconds = 300

        lt = dt.datetime(2024, 1, 1, 10, 30)
        task = CronTask(
            id="t1", name="test", schedule="30 * * * *",
            description="", agent_id="main_agent", session_id="default",
            enabled=True, last_triggered=lt,
        )
        sched._tasks["t1"] = task
        sched.save_tasks()

        data = json.loads(tasks_file.read_text())
        assert len(data) == 1
        assert data[0]["last_triggered"] == "2024-01-01T10:30:00"

    def test_load_restores_last_triggered(self, tmp_path):
        from gateway.cron_scheduler import CronScheduler
        import datetime as dt

        tasks_file = tmp_path / "tasks.json"
        tasks_file.parent.mkdir(parents=True, exist_ok=True)
        tasks_file.write_text(json.dumps([{
            "id": "t1", "name": "test", "schedule": "30 * * * *",
            "description": "", "agent_id": "main_agent", "session_id": "default",
            "enabled": True, "last_triggered": "2024-01-01T10:30:00",
        }]))

        sched = CronScheduler.__new__(CronScheduler)
        sched._task_file = tasks_file
        sched._tasks = {}
        sched._running = False
        sched._runner_task = None
        sched._queues = {}
        sched._processing = {}
        sched._push_callback = None
        sched._max_missed_seconds = 300

        sched.load_tasks()
        task = sched._tasks.get("t1")
        assert task is not None
        assert task.last_triggered == dt.datetime(2024, 1, 1, 10, 30)

    def test_load_missing_last_triggered_is_none(self, tmp_path):
        from gateway.cron_scheduler import CronScheduler

        tasks_file = tmp_path / "tasks.json"
        tasks_file.parent.mkdir(parents=True, exist_ok=True)
        tasks_file.write_text(json.dumps([{
            "id": "t1", "name": "test", "schedule": "30 * * * *",
            "enabled": True,
        }]))

        sched = CronScheduler.__new__(CronScheduler)
        sched._task_file = tasks_file
        sched._tasks = {}
        sched._running = False
        sched._runner_task = None
        sched._queues = {}
        sched._processing = {}
        sched._push_callback = None
        sched._max_missed_seconds = 300

        sched.load_tasks()
        task = sched._tasks.get("t1")
        assert task is not None
        assert task.last_triggered is None


class TestCronSchedulerInit:
    """CronScheduler 构造参数测试"""

    def test_default_max_missed_seconds(self):
        from gateway.cron_scheduler import CronScheduler
        sched = CronScheduler()
        assert sched._max_missed_seconds == 300

    def test_custom_max_missed_seconds(self):
        from gateway.cron_scheduler import CronScheduler
        sched = CronScheduler(max_missed_seconds=60)
        assert sched._max_missed_seconds == 60


# ============================================================
# 磁盘合并保护测试 — 验证外部写入不会被 save_tasks 覆盖
# ============================================================


def _make_bare_scheduler(tmp_path, tasks=None):
    """创建一个挂载到临时目录的 CronScheduler，不启动事件循环"""
    from gateway.cron_scheduler import CronScheduler
    sched = CronScheduler.__new__(CronScheduler)
    sched._task_file = tmp_path / "tasks.json"
    sched._tasks = {}
    sched._running = False
    sched._runner_task = None
    sched._queues = {}
    sched._processing = {}
    sched._push_callback = None
    sched._max_missed_seconds = 300
    if tasks:
        for t in tasks:
            sched._tasks[t.id] = t
    return sched


def _write_tasks_file(tmp_path, tasks_list):
    """向临时目录写入 tasks.json"""
    tmp_path.mkdir(parents=True, exist_ok=True)
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps(tasks_list, indent=2))


class TestMergeDiskTasks:
    """测试 _merge_disk_tasks — 从磁盘同步外部新增任务"""

    def test_adds_new_tasks_from_disk(self, tmp_path):
        """磁盘有 2 个任务，内存只有 1 个 → 合并后内存应有 2 个"""
        _write_tasks_file(tmp_path, [
            {"id": "t1", "name": "task1", "schedule": "0 9 * * *", "enabled": True},
            {"id": "t2", "name": "task2", "schedule": "30 * * * *", "enabled": True},
        ])
        t1 = _make_task("t1", schedule="0 9 * * *")
        sched = _make_bare_scheduler(tmp_path, [t1])

        sched._merge_disk_tasks()

        assert "t1" in sched._tasks
        assert "t2" in sched._tasks
        assert sched._tasks["t2"].name == "task2"
        assert sched._tasks["t2"].schedule == "30 * * * *"

    def test_does_not_overwrite_existing(self, tmp_path):
        """内存中的任务（含 last_triggered）不会被磁盘版本覆盖"""
        import datetime as dt
        _write_tasks_file(tmp_path, [
            {"id": "t1", "name": "disk_version", "schedule": "0 9 * * *", "enabled": True},
        ])
        lt = dt.datetime(2024, 1, 1, 10, 30)
        t1 = _make_task("t1", schedule="30 * * * *", last_triggered=lt)
        t1.name = "memory_version"
        sched = _make_bare_scheduler(tmp_path, [t1])

        sched._merge_disk_tasks()

        assert sched._tasks["t1"].name == "memory_version"
        assert sched._tasks["t1"].schedule == "30 * * * *"
        assert sched._tasks["t1"].last_triggered == lt

    def test_empty_disk_does_nothing(self, tmp_path):
        """磁盘文件为空 JSON 数组 → 不影响内存"""
        _write_tasks_file(tmp_path, [])
        t1 = _make_task("t1", schedule="0 9 * * *")
        sched = _make_bare_scheduler(tmp_path, [t1])

        sched._merge_disk_tasks()

        assert len(sched._tasks) == 1
        assert "t1" in sched._tasks

    def test_no_file_does_nothing(self, tmp_path):
        """磁盘文件不存在 → 不影响内存"""
        t1 = _make_task("t1", schedule="0 9 * * *")
        sched = _make_bare_scheduler(tmp_path, [t1])

        sched._merge_disk_tasks()

        assert len(sched._tasks) == 1
        assert "t1" in sched._tasks

    def test_corrupt_json_does_not_crash(self, tmp_path):
        """磁盘 JSON 损坏 → 静默跳过，不影响内存"""
        tasks_file = tmp_path / "tasks.json"
        tmp_path.mkdir(parents=True, exist_ok=True)
        tasks_file.write_text("{corrupt")
        t1 = _make_task("t1", schedule="0 9 * * *")
        sched = _make_bare_scheduler(tmp_path, [t1])

        sched._merge_disk_tasks()

        assert len(sched._tasks) == 1
        assert "t1" in sched._tasks


class TestSaveTasksPreservesExternal:
    """测试 save_tasks() 不会覆盖磁盘上外部新增的任务"""

    def test_preserves_externally_added_task(self, tmp_path):
        """内存有[t1, t2]，磁盘有[t1, t2, t3(AI新增)] → save 后磁盘保留 t3"""
        _write_tasks_file(tmp_path, [
            {"id": "t1", "name": "task1", "schedule": "0 9 * * *"},
            {"id": "t2", "name": "task2", "schedule": "30 * * * *"},
            {"id": "t3", "name": "ai_added", "schedule": "0 6 * * *",
             "description": "AI agent 新增", "agent_id": "main_agent",
             "session_id": "sess1", "enabled": True},
        ])
        t1 = _make_task("t1", schedule="0 9 * * *")
        t2 = _make_task("t2", schedule="30 * * * *")
        sched = _make_bare_scheduler(tmp_path, [t1, t2])

        sched.save_tasks()

        data = json.loads((tmp_path / "tasks.json").read_text())
        ids = [t["id"] for t in data]
        assert "t1" in ids
        assert "t2" in ids
        assert "t3" in ids
        t3 = next(t for t in data if t["id"] == "t3")
        assert t3["name"] == "ai_added"
        assert t3["schedule"] == "0 6 * * *"

    def test_preserves_last_triggered_on_save(self, tmp_path):
        """内存中的 last_triggered 更新后保存，外部任务不被影响"""
        import datetime as dt
        lt = dt.datetime(2024, 6, 1, 9, 0)
        _write_tasks_file(tmp_path, [
            {"id": "t1", "name": "task1", "schedule": "0 9 * * *",
             "last_triggered": None},
            {"id": "t2", "name": "external_new", "schedule": "0 12 * * *",
             "enabled": True},
        ])
        t1 = _make_task("t1", schedule="0 9 * * *", last_triggered=lt)
        sched = _make_bare_scheduler(tmp_path, [t1])

        sched.save_tasks()

        data = json.loads((tmp_path / "tasks.json").read_text())
        t1_data = next(t for t in data if t["id"] == "t1")
        assert t1_data["last_triggered"] == "2024-06-01T09:00:00"
        t2_data = next(t for t in data if t["id"] == "t2")
        assert t2_data["name"] == "external_new"


class TestCheckAndTriggerMergesExternal:
    """测试 _check_and_trigger 自动同步外部新增任务"""

    @pytest.mark.asyncio
    async def test_picks_up_external_task(self, tmp_path):
        """scheduler 内存有 t1，磁盘新写入 t2 → 下一轮检查自动同步 t2"""
        _write_tasks_file(tmp_path, [
            {"id": "t1", "name": "task1", "schedule": "30 * * * *", "enabled": True},
            {"id": "t2", "name": "external", "schedule": "30 * * * *", "enabled": True,
             "agent_id": "main_agent", "session_id": "default", "description": "ext"},
        ])
        t1 = _make_task("t1", schedule="30 * * * *")
        sched = _make_bare_scheduler(tmp_path, [t1])

        assert "t2" not in sched._tasks

        now = datetime.datetime(2024, 1, 1, 10, 31, 0)
        triggered = await _run_check(sched, now)

        assert "t2" in sched._tasks
        assert "t1" in triggered

    @pytest.mark.asyncio
    async def test_external_task_can_trigger(self, tmp_path):
        """外部新增的 t2 在同步后能正常被触发"""
        now = datetime.datetime(2024, 1, 1, 10, 31, 0)
        _write_tasks_file(tmp_path, [
            {"id": "t1", "name": "task1", "schedule": "30 * * * *", "enabled": True},
            {"id": "t2", "name": "external", "schedule": "0 10 * * *", "enabled": True,
             "agent_id": "main_agent", "session_id": "default", "description": "ext"},
        ])
        t1 = _make_task("t1", schedule="30 * * * *")
        sched = _make_bare_scheduler(tmp_path, [t1])
        sched._max_missed_seconds = 3600

        triggered = await _run_check(sched, now)

        assert "t2" in triggered
        assert sched._tasks["t2"].last_triggered == datetime.datetime(2024, 1, 1, 10, 0)

    @pytest.mark.asyncio
    async def test_external_disabled_task_not_triggered(self, tmp_path):
        """外部新增但 disabled 的任务不触发"""
        now = datetime.datetime(2024, 1, 1, 10, 31, 0)
        _write_tasks_file(tmp_path, [
            {"id": "t1", "name": "task1", "schedule": "30 * * * *", "enabled": True},
            {"id": "t2", "name": "disabled_ext", "schedule": "30 * * * *", "enabled": False,
             "agent_id": "main_agent", "session_id": "default", "description": "ext"},
        ])
        t1 = _make_task("t1", schedule="30 * * * *")
        sched = _make_bare_scheduler(tmp_path, [t1])

        triggered = await _run_check(sched, now)

        assert "t2" in sched._tasks
        assert "t2" not in triggered


class TestEndToEndExternalWriteSurvival:
    """端到端：模拟 AI 外部写入 → scheduler 不丢数据"""

    @pytest.mark.asyncio
    async def test_ai_writes_then_scheduler_saves_preserves(self, tmp_path):
        """模拟完整场景：
        1. scheduler 启动，加载 [t1, t2]
        2. AI 外部写入 tasks.json，新增 t3
        3. scheduler _check_and_trigger 运行，t1 触发 → save_tasks
        4. 验证 t3 未被覆盖
        """
        import datetime as dt

        _write_tasks_file(tmp_path, [
            {"id": "t1", "name": "task1", "schedule": "30 * * * *", "enabled": True},
            {"id": "t2", "name": "task2", "schedule": "0 9 * * *", "enabled": True},
        ])
        t1 = _make_task("t1", schedule="30 * * * *")
        t2 = _make_task("t2", schedule="0 9 * * *")
        sched = _make_bare_scheduler(tmp_path, [t1, t2])

        now = dt.datetime(2024, 1, 1, 11, 31, 0)

        ai_task = {
            "id": "t3",
            "name": "hn_agent_daily",
            "schedule": "0 6 * * *",
            "description": "Hacker News 智能体日报",
            "agent_id": "main_agent",
            "session_id": "sess_ai",
            "enabled": True,
        }

        triggered = set()

        async def fake_enqueue(task):
            triggered.add(task.id)
            current = json.loads((tmp_path / "tasks.json").read_text())
            current.append(ai_task)
            (tmp_path / "tasks.json").write_text(json.dumps(current, indent=2))

        original = sched._enqueue_message
        sched._enqueue_message = fake_enqueue

        await sched._check_and_trigger(_now=now)

        sched._enqueue_message = original

        data = json.loads((tmp_path / "tasks.json").read_text())
        ids = {t["id"] for t in data}
        assert "t1" in ids
        assert "t2" in ids
        assert "t3" in ids

        t3_data = next(t for t in data if t["id"] == "t3")
        assert t3_data["name"] == "hn_agent_daily"
        assert t3_data["schedule"] == "0 6 * * *"
