""""EventBus 事件总线测试"""

import pytest
import asyncio

from fastmind import Event


@pytest.fixture
def event_bus():
    from gateway.event_bus import EventBus
    return EventBus()


class TestEventBusSubscribe:
    """订阅 / 取消订阅"""

    @pytest.mark.asyncio
    async def test_subscribe_returns_queue(self, event_bus):
        queue = event_bus.subscribe("session_1")
        assert isinstance(queue, asyncio.Queue)

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_queue(self, event_bus):
        queue = event_bus.subscribe("session_1")
        event_bus.unsubscribe("session_1", queue)
        assert len(event_bus._subscribers["session_1"]) == 0

    @pytest.mark.asyncio
    async def test_multiple_subscribers_same_session(self, event_bus):
        event_bus.subscribe("s1")
        event_bus.subscribe("s1")
        assert len(event_bus._subscribers["s1"]) == 2


class TestEventBusPublish:
    """发布事件"""

    @pytest.mark.asyncio
    async def test_publish_delivers_to_subscriber(self, event_bus):
        queue = event_bus.subscribe("s1")
        event = Event("test.type", {"key": "value"}, "s1")
        await event_bus.publish("s1", event)

        received = await asyncio.wait_for(queue.get(), timeout=1)
        assert received.type == "test.type"
        assert received.payload["key"] == "value"
        assert received.session_id == "s1"

    @pytest.mark.asyncio
    async def test_publish_delivers_to_all_subscribers(self, event_bus):
        q1 = event_bus.subscribe("s1")
        q2 = event_bus.subscribe("s1")
        event = Event("test", {}, "s1")
        await event_bus.publish("s1", event)

        r1 = await asyncio.wait_for(q1.get(), timeout=1)
        r2 = await asyncio.wait_for(q2.get(), timeout=1)
        assert r1.type == "test"
        assert r2.type == "test"

    @pytest.mark.asyncio
    async def test_publish_unsubscribed_session_no_error(self, event_bus):
        event = Event("test", {}, "no_subs")
        await event_bus.publish("no_subs", event)


class TestEventBusPush:
    """推送事件（含 API 调用）"""

    @pytest.mark.asyncio
    async def test_push_calls_api_when_set(self, event_bus):
        calls = []

        class MockAPI:
            async def push_event(self, session_id, event):
                calls.append((session_id, event.type))

        event_bus.set_api(MockAPI())
        event = Event("user.message", {"text": "hi"}, "s1")
        await event_bus.push("s1", event)

        assert len(calls) == 1
        assert calls[0] == ("s1", "user.message")

    @pytest.mark.asyncio
    async def test_push_noop_when_api_not_set(self, event_bus):
        event = Event("user.message", {"text": "hi"}, "s1")
        await event_bus.push("s1", event)


class TestEventBusMessageId:
    """消息 ID 生成"""

    def test_generate_message_id_is_unique(self, event_bus):
        ids = {event_bus.generate_message_id() for _ in range(100)}
        assert len(ids) == 100
        for mid in ids:
            assert mid.startswith("msg_")

    def test_generate_cron_id_contains_task_id(self, event_bus):
        cid = event_bus.generate_cron_id("task_001")
        assert cid.startswith("cron_task_001_")
        assert len(cid) > len("cron_task_001_")


class TestStreamMessage:
    """StreamMessage 数据类"""

    def test_default_values(self):
        from gateway.event_bus import StreamMessage
        msg = StreamMessage(message_id="m1")
        assert msg.message_id == "m1"
        assert msg.role == "assistant"
        assert msg.payload == {}
        assert msg.timestamp == 0

    def test_full_creation(self):
        from gateway.event_bus import StreamMessage
        msg = StreamMessage(
            message_id="m1",
            client_message_id="c1",
            session_id="s1",
            role="user",
            event_type="stream.chunk",
            payload={"delta": "hi"},
            timestamp=1.5,
        )
        assert msg.role == "user"
        assert msg.event_type == "stream.chunk"
        assert msg.payload["delta"] == "hi"


class TestGlobalEventBus:
    """全局 EventBus 单例"""

    def test_get_event_bus_is_singleton(self):
        from gateway.event_bus import get_event_bus, set_event_bus, EventBus
        bus_a = EventBus()
        set_event_bus(bus_a)
        bus_b = get_event_bus()
        assert bus_a is bus_b

    def test_get_event_bus_creates_lazily(self):
        from gateway.event_bus import get_event_bus, set_event_bus
        set_event_bus(None)
        import gateway.event_bus as mod
        mod._event_bus = None
        bus = get_event_bus()
        assert bus is not None
