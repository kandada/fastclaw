"""感知循环测试"""

import pytest
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "vendor"))

from fastmind import FastMind, Event
from fastmind.core.perception import PerceptionScheduler, PerceptionLoop


class TestPerceptionLoop:
    """感知循环测试"""

    @pytest.mark.asyncio
    async def test_perception_loop_start_stop(self):
        """测试感知循环启动和停止"""

        async def dummy_perception(app):
            while True:
                yield Event("test", {}, "default")
                await asyncio.sleep(0.1)

        loop = PerceptionLoop("test_loop", dummy_perception, 1.0)

        events_received = []

        async def handler(event):
            events_received.append(event)

        await loop.start(handler)
        await asyncio.sleep(0.3)
        await loop.stop()

        assert len(events_received) >= 1

    @pytest.mark.asyncio
    async def test_perception_loop_interval(self):
        """测试感知循环间隔"""
        call_count = 0

        async def counting_perception(app):
            nonlocal call_count
            while True:
                call_count += 1
                yield Event("test", {}, "default")
                await asyncio.sleep(0.05)

        loop = PerceptionLoop("counting", counting_perception, 0.1)

        async def handler(event):
            pass

        await loop.start(handler)
        await asyncio.sleep(0.2)
        await loop.stop()

        assert call_count >= 1


class TestPerceptionScheduler:
    """感知调度器测试"""

    @pytest.mark.asyncio
    async def test_scheduler_register_loop(self):
        """测试调度器注册循环"""
        scheduler = PerceptionScheduler(FastMind())

        async def dummy_perception(app):
            while True:
                yield Event("test", {}, "default")
                await asyncio.sleep(0.1)

        scheduler.register_loop("test", dummy_perception, 1.0)

        loops = scheduler.list_loops()
        assert "test" in loops

    @pytest.mark.asyncio
    async def test_scheduler_get_loop(self):
        """测试调度器获取循环"""
        scheduler = PerceptionScheduler(FastMind())

        async def dummy_perception(app):
            while True:
                yield Event("test", {}, "default")
                await asyncio.sleep(0.1)

        scheduler.register_loop("test", dummy_perception, 1.0)

        loop = scheduler.get_loop("test")
        assert loop is not None
        assert loop.name == "test"

    @pytest.mark.asyncio
    async def test_scheduler_start_stop(self):
        """测试调度器启动和停止"""
        app = FastMind()
        scheduler = PerceptionScheduler(app)

        async def dummy_perception(app):
            while True:
                yield Event("test", {}, "default")
                await asyncio.sleep(0.01)

        scheduler.register_loop("test", dummy_perception, 0.1)

        await scheduler.start()
        await asyncio.sleep(0.1)
        await scheduler.stop()

        assert len(scheduler.list_loops()) == 0


class TestEventFormat:
    """事件格式测试"""

    def test_event_basic(self):
        """测试基本事件"""
        event = Event("test", {"key": "value"}, "session1")

        assert event.type == "test"
        assert event.payload["key"] == "value"
        assert event.session_id == "session1"

    def test_event_session_id(self):
        """测试事件 session_id"""
        event = Event("test", {}, "my_session")
        assert event.session_id == "my_session"

    def test_event_payload(self):
        """测试事件 payload"""
        event = Event(
            "cron.triggered",
            {"task_id": "123", "task_name": "test"},
            "session1",
        )

        assert event.payload["task_id"] == "123"
        assert event.payload["task_name"] == "test"


class TestSensorData:
    """传感器数据事件测试"""

    def test_sensor_data_event(self):
        """测试传感器数据事件"""
        event = Event(
            "sensor.data",
            {"sensor": "temperature", "data": 25.5},
            "system",
        )

        assert event.type == "sensor.data"
        assert event.payload["sensor"] == "temperature"
        assert event.payload["data"] == 25.5
