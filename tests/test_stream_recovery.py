# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""流式状态恢复 / 断线续传 / message_id 贯穿 专项测试

覆盖接口层修复：
- app.py: message_id 贯穿到所有 stream.* 输出事件
- router.py: 订阅无关的会话流状态累积任务（_session_stream_state 常驻化）
- router.py: 可续传 SSE（?cursor 回放）
- router.py: cron 元信息挂载（_pending_cron_info -> 累积状态）
"""

import asyncio
import time

import pytest
from fastmind import Event
from fastmind.core.engine import EventBuffer

import gateway.router as router


# ---------------------------------------------------------------------------
# 工具 & fixtures
# ---------------------------------------------------------------------------
class FakeSession:
    """仅暴露 _event_buffer 和 is_alive 的最小会话对象（用于测试累积/续传）"""

    def __init__(self):
        self._event_buffer = EventBuffer(maxlen=5000)
        self.is_alive = True

    async def stop(self):
        self.is_alive = False


class FakeEngine:
    """最小引擎：get_or_create_session 会自动创建 FakeSession"""

    def __init__(self, sessions):
        self._sessions = sessions

    def get_or_create_session(self, session_id):
        if session_id not in self._sessions:
            self._sessions[session_id] = FakeSession()
        return self._sessions[session_id]

    async def delete_session(self, session_id):
        self._sessions.pop(session_id, None)


class FakeAPI:
    def __init__(self, sessions=None):
        self._sessions = sessions or {}
        self._engine = FakeEngine(self._sessions)
        self.deleted = []
        self.pushed = []

    def get_session(self, session_id):
        return self._sessions.get(session_id)

    async def delete_session(self, session_id):
        self.deleted.append(session_id)
        await self._engine.delete_session(session_id)

    async def push_event(self, session_id, event):
        self.pushed.append((session_id, event))


def _ev(etype, payload, sid="s1"):
    return Event(type=etype, payload=payload, session_id=sid)


@pytest.fixture(autouse=True)
def _clean_stream_state():
    """每个用例前后清理累积状态相关全局变量，避免相互污染"""
    router._session_stream_state.clear()
    router._session_state_cursors.clear()
    router._pending_cron_info.clear()
    for t in list(router._accumulator_tasks.values()):
        if not t.done():
            t.cancel()
    router._accumulator_tasks.clear()
    yield
    router._session_stream_state.clear()
    router._session_state_cursors.clear()
    router._pending_cron_info.clear()
    for t in list(router._accumulator_tasks.values()):
        if not t.done():
            t.cancel()
    router._accumulator_tasks.clear()


def _set_api(sessions=None):
    api = FakeAPI(sessions)
    router.set_websocket_api(api)
    return api


def _reset_api():
    router.set_websocket_api(None)


async def _stop_task(task):
    """取消并等待累积任务结束（其 wait 使用 15s 超时，直接 await 会拖慢测试）"""
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------------------
# 1. message_id 贯穿：_transform_event_to_sse 的 data 与 id 都携带 message_id
# ---------------------------------------------------------------------------
class TestMessageIdThreading:
    def test_chunk_carries_message_id(self):
        sse = router._transform_event_to_sse(
            _ev("stream.chunk", {"delta": "hi", "message_id": "msg-1"})
        )
        assert sse["id"] == "msg-1"
        assert sse["data"]["message_id"] == "msg-1"

    def test_tool_result_carries_message_id(self):
        sse = router._transform_event_to_sse(
            _ev(
                "stream.tool_result",
                {"tool_call_id": "c", "tool_name": "t", "result": "r", "message_id": "m"},
            )
        )
        assert sse["id"] == "m"
        assert sse["data"]["message_id"] == "m"

    def test_tool_start_synthesized_data_gets_message_id(self):
        sse = router._transform_event_to_sse(
            _ev(
                "stream.fragment",
                {
                    "has_tool_calls": True,
                    "tool_calls": [{"id": "c1", "function": {"name": "run_shell", "arguments": "{}"}}],
                    "message_id": "m2",
                },
            )
        )
        assert sse["event"] == "message.tool_start"
        assert sse["id"] == "m2"
        assert sse["data"]["message_id"] == "m2"

    def test_error_gets_message_id(self):
        sse = router._transform_event_to_sse(
            _ev("stream.error", {"error": "boom", "message_id": "m3"})
        )
        assert sse["id"] == "m3"
        assert sse["data"]["message_id"] == "m3"

    def test_no_message_id_fallback_unknown(self):
        """旧渠道无 message_id 时仍回退 unknown（不破坏既有行为）"""
        sse = router._transform_event_to_sse(_ev("stream.chunk", {"delta": "x"}))
        assert sse["id"] == "unknown"


# ---------------------------------------------------------------------------
# 2. 订阅无关的累积：_accumulate_event
# ---------------------------------------------------------------------------
class TestAccumulateEvent:
    def test_initializes_state_with_cron_meta(self):
        router._session_state_cursors["s1"] = 10
        # 以 message_id 为 key 的待处理 cron 信息
        router._pending_cron_info["m"] = {
            "task_id": "t1", "task_name": "daily", "trigger_time": "09:00",
        }
        router._accumulate_event("s1", _ev("stream.chunk", {"delta": "hi", "message_id": "m"}))
        state = router._session_stream_state["s1"]
        assert state["message_id"] == "m"
        assert state["content"] == "hi"
        assert state["is_cron"] is True
        assert state["task_id"] == "t1"
        assert state["task_name"] == "daily"
        assert state["cursor"] == 10

    def test_accumulates_content_and_thinking(self):
        router._session_state_cursors["s1"] = 1
        router._accumulate_event("s1", _ev("stream.chunk", {"delta": "a", "message_id": "m"}))
        router._accumulate_event("s1", _ev("stream.chunk", {"delta": "b", "message_id": "m"}))
        router._accumulate_event("s1", _ev("stream.thinking", {"delta": "t", "message_id": "m"}))
        state = router._session_stream_state["s1"]
        assert state["content"] == "ab"
        assert state["thinking"] == "t"

    def test_multiple_cron_messages_isolated_by_message_id(self):
        """同一 session 连续多个 cron 任务，元信息按 message_id 隔离不互相覆盖"""
        router._pending_cron_info["m1"] = {"task_id": "t1", "task_name": "first", "trigger_time": "09:00"}
        router._pending_cron_info["m2"] = {"task_id": "t2", "task_name": "second", "trigger_time": "10:00"}
        router._accumulate_event("s1", _ev("stream.chunk", {"delta": "a", "message_id": "m1"}))
        assert router._session_stream_state["s1"]["task_id"] == "t1"
        router._accumulate_event("s1", _ev("stream.end", {"message_id": "m1"}))
        router._accumulate_event("s1", _ev("stream.chunk", {"delta": "b", "message_id": "m2"}))
        assert router._session_stream_state["s1"]["task_id"] == "t2"
        assert router._session_stream_state["s1"]["task_name"] == "second"

    def test_accumulates_tool_calls_and_results(self):
        router._session_state_cursors["s1"] = 1
        router._accumulate_event(
            "s1",
            _ev(
                "stream.fragment",
                {
                    "has_tool_calls": True,
                    "tool_calls": [{"id": "c1", "function": {"name": "run_shell", "arguments": "{}"}}],
                    "message_id": "m",
                },
            ),
        )
        router._accumulate_event(
            "s1",
            _ev(
                "stream.tool_result",
                {"tool_call_id": "c1", "tool_name": "run_shell", "result": "out", "message_id": "m"},
            ),
        )
        state = router._session_stream_state["s1"]
        assert len(state["tool_calls"]) == 1
        assert len(state["tool_results"]) == 1
        assert state["tool_results"][0]["result"] == "out"

    def test_end_pops_state(self):
        router._accumulate_event("s1", _ev("stream.chunk", {"delta": "x", "message_id": "m"}))
        assert "s1" in router._session_stream_state
        router._accumulate_event("s1", _ev("stream.end", {"message_id": "m"}))
        assert "s1" not in router._session_stream_state

    def test_error_pops_state(self):
        router._accumulate_event("s1", _ev("stream.chunk", {"delta": "x", "message_id": "m"}))
        router._accumulate_event("s1", _ev("stream.error", {"error": "e", "message_id": "m"}))
        assert "s1" not in router._session_stream_state

    def test_ignores_user_and_cron_message(self):
        router._accumulate_event("s1", _ev("user.message", {"text": "hi"}))
        router._accumulate_event("s1", _ev("cron.message", {}))
        assert "s1" not in router._session_stream_state


# ---------------------------------------------------------------------------
# 3. 常驻累积任务：_run_session_accumulator（订阅无关）
# ---------------------------------------------------------------------------
class TestSessionAccumulatorTask:
    @pytest.mark.asyncio
    async def test_drains_without_sse_subscription(self):
        fake = FakeSession()
        _set_api({"s1": fake})

        router.ensure_session_accumulator("s1")
        await asyncio.sleep(0.05)  # 让任务启动并确定起始游标
        fake._event_buffer.append(_ev("stream.chunk", {"delta": "hello", "message_id": "m"}))
        fake._event_buffer.append(_ev("stream.thinking", {"delta": "think", "message_id": "m"}))

        for _ in range(200):
            await asyncio.sleep(0.01)
            state = router._session_stream_state.get("s1")
            if state and state.get("content") == "hello" and state.get("thinking") == "think":
                break

        assert router._session_stream_state["s1"]["content"] == "hello"
        assert router._session_stream_state["s1"]["thinking"] == "think"
        # 游标应已推进
        assert router._session_state_cursors.get("s1", 0) >= 2

        fake.is_alive = False
        task = router._accumulator_tasks.pop("s1", None)
        await _stop_task(task)
        _reset_api()

    @pytest.mark.asyncio
    async def test_task_cleans_up_on_end(self):
        fake = FakeSession()
        _set_api({"s1": fake})

        router.ensure_session_accumulator("s1")
        assert "s1" in router._accumulator_tasks
        await asyncio.sleep(0.05)
        fake._event_buffer.append(_ev("stream.chunk", {"delta": "x", "message_id": "m"}))
        fake._event_buffer.append(_ev("stream.end", {"message_id": "m"}))

        await asyncio.sleep(0.2)  # 等累积任务处理完 chunk+end 批次

        # end 到达后状态被清空
        assert "s1" not in router._session_stream_state
        # 任务仍存活等待下一条消息（未被清理）
        assert router._accumulator_tasks.get("s1") is not None

        fake.is_alive = False
        task = router._accumulator_tasks.pop("s1", None)
        await _stop_task(task)
        _reset_api()


# ---------------------------------------------------------------------------
# 4. 可续传 SSE：_stream_session_events 的 start_cursor 回放
# ---------------------------------------------------------------------------
class TestStreamResume:
    async def _collect(self, agen, limit=50):
        out = []
        async for ev in agen:
            if ev is not None:
                out.append(ev)
            if len(out) >= limit:
                break
        return out

    @pytest.mark.asyncio
    async def test_replay_from_cursor(self):
        fake = FakeSession()
        fake._event_buffer.append(_ev("stream.chunk", {"delta": "1", "message_id": "m"}))
        fake._event_buffer.append(_ev("stream.chunk", {"delta": "2", "message_id": "m"}))
        fake._event_buffer.append(_ev("stream.end", {"message_id": "m"}))
        tail = fake._event_buffer.tail_cursor

        # 从游标 1 回放，应只拿到第 2、3 个事件（跳过第 1 个）
        events = await self._collect(
            router._stream_session_events(fake, start_cursor=1)
        )
        assert len(events) == 2
        assert events[0].payload["delta"] == "2"
        assert events[1].type == "stream.end"

        # 默认 tail 起播（start_cursor=None）应不返回历史事件
        fake.is_alive = False
        events_tail = await self._collect(
            router._stream_session_events(fake, start_cursor=None)
        )
        assert events_tail == []

    @pytest.mark.asyncio
    async def test_replay_from_zero_replays_all(self):
        fake = FakeSession()
        fake._event_buffer.append(_ev("stream.chunk", {"delta": "a", "message_id": "m"}))
        fake._event_buffer.append(_ev("stream.chunk", {"delta": "b", "message_id": "m"}))
        fake._event_buffer.append(_ev("stream.end", {"message_id": "m"}))
        events = await self._collect(router._stream_session_events(fake, start_cursor=0))
        assert [e.payload["delta"] for e in events if e.type == "stream.chunk"] == ["a", "b"]
        assert events[-1].type == "stream.end"

    @pytest.mark.asyncio
    async def test_replay_cursor_beyond_tail_returns_empty(self):
        """start_cursor 超过当前尾部时不应报错，直接等待/返回空"""
        fake = FakeSession()
        fake._event_buffer.append(_ev("stream.chunk", {"delta": "a", "message_id": "m"}))
        fake.is_alive = False
        events = await self._collect(
            router._stream_session_events(fake, start_cursor=9999)
        )
        assert events == []

    @pytest.mark.asyncio
    async def test_replay_cursor_before_base_clamps(self):
        """start_cursor 小于 base（环形缓冲被淘汰）时应从 base 回放而非崩溃"""
        small = FakeSession()
        small._event_buffer = EventBuffer(maxlen=10)
        for i in range(15):
            small._event_buffer.append(_ev("stream.chunk", {"delta": str(i), "message_id": "m"}))
        small._event_buffer.append(_ev("stream.end", {"message_id": "m"}))
        # 15 个 chunk + 1 个 end，maxlen=10：base 推进，start_cursor=0 被 clamp 到 base
        events = await self._collect(
            router._stream_session_events(small, start_cursor=0)
        )
        assert events[-1].type == "stream.end"
        # 被淘汰的部分不再可见，从 base 开始回放
        deltas = [e.payload["delta"] for e in events if e.type == "stream.chunk"]
        assert deltas == [str(i) for i in range(6, 15)]


# ---------------------------------------------------------------------------
# 5. chat_stream_state 返回 cursor（供前端续传）
# ---------------------------------------------------------------------------
class TestChatStreamStateCursor:
    def test_returns_cursor_when_in_flight(self):
        router._session_state_cursors["s1"] = 42
        router._accumulate_event("s1", _ev("stream.chunk", {"delta": "x", "message_id": "m"}))
        state = asyncio.run(router.chat_stream_state("s1"))
        assert state["message_id"] == "m"
        assert state["cursor"] == 42

    def test_default_state_has_cursor_none(self):
        state = asyncio.run(router.chat_stream_state("nonexistent"))
        assert state["message_id"] is None
        assert state["cursor"] is None


# ---------------------------------------------------------------------------
# 6. 累积任务启动：ensure_session_accumulator
# ---------------------------------------------------------------------------
class TestEnsureAccumulator:
    @pytest.mark.asyncio
    async def test_starts_task_when_api_has_session(self):
        fake = FakeSession()
        api = _set_api({"s1": fake})
        router.ensure_session_accumulator("s1")
        assert "s1" in router._accumulator_tasks
        assert not router._accumulator_tasks["s1"].done()
        task = router._accumulator_tasks.pop("s1", None)
        await _stop_task(task)
        _reset_api()

    @pytest.mark.asyncio
    async def test_no_task_when_no_api(self):
        _reset_api()
        router.ensure_session_accumulator("s1")
        assert "s1" not in router._accumulator_tasks

    @pytest.mark.asyncio
    async def test_creates_session_and_starts_task_when_missing(self):
        """session 尚未创建时，ensure 会通过 engine.get_or_create 先建 session 再启动累积任务"""
        api = _set_api({})  # 无任何会话，但带 engine
        router.ensure_session_accumulator("s1")
        assert "s1" in router._accumulator_tasks
        assert "s1" in api._sessions  # session 已被创建
        task = router._accumulator_tasks.pop("s1", None)
        await _stop_task(task)
        _reset_api()

    @pytest.mark.asyncio
    async def test_no_task_when_no_engine(self):
        """api 存在但无 engine（get_or_create 不可用）时，不启动累积任务"""
        api = _set_api({})
        api._engine = None
        router.ensure_session_accumulator("s1")
        assert "s1" not in router._accumulator_tasks
        _reset_api()

    @pytest.mark.asyncio
    async def test_no_duplicate_task(self):
        fake = FakeSession()
        _set_api({"s1": fake})
        router.ensure_session_accumulator("s1")
        first = router._accumulator_tasks["s1"]
        router.ensure_session_accumulator("s1")
        assert router._accumulator_tasks["s1"] is first
        task = router._accumulator_tasks.pop("s1", None)
        await _stop_task(task)
        _reset_api()


# ---------------------------------------------------------------------------
# 7. chat_stop 清理累积状态
# ---------------------------------------------------------------------------
class TestChatStopCleanup:
    @pytest.mark.asyncio
    async def test_chat_stop_clears_accumulator_state(self):
        fake = FakeSession()
        fake.is_alive = False  # 模拟已停止
        _set_api({"s1": fake})
        router._session_stream_state["s1"] = {"message_id": "m"}
        router._session_state_cursors["s1"] = 5
        result = await router.chat_stop("s1")
        assert result["status"] == "stopped"
        assert "s1" not in router._session_stream_state
        assert "s1" not in router._session_state_cursors
        assert "s1" not in router._accumulator_tasks
        _reset_api()


# ---------------------------------------------------------------------------
# 8. delete_session 清理（流状态 / 累积任务 / cron 队列 / 引擎 session）
# ---------------------------------------------------------------------------
class TestDeleteSessionCleanup:
    @pytest.mark.asyncio
    async def test_delete_session_cleans_up(self, monkeypatch):
        fake = FakeSession()
        api = _set_api({"s1": fake})
        router._session_stream_state["s1"] = {"message_id": "m"}
        router._session_state_cursors["s1"] = 5
        router._cron_sse_queues["s1"] = asyncio.Queue()
        router.ensure_session_accumulator("s1")

        monkeypatch.setattr(
            router, "_load_sessions_async",
            _async_return({"s1": {"session_id": "s1"}}),
        )
        monkeypatch.setattr(router, "_save_sessions_async", _noop)

        result = await router.delete_session("s1")

        assert result["status"] == "deleted"
        assert "s1" not in router._session_stream_state
        assert "s1" not in router._session_state_cursors
        assert "s1" not in router._accumulator_tasks
        assert "s1" not in router._cron_sse_queues
        # 引擎层面 session 被删除
        assert "s1" in api.deleted
        assert "s1" not in api._sessions
        _reset_api()

    @pytest.mark.asyncio
    async def test_delete_session_404_when_missing(self, monkeypatch):
        _set_api({})
        monkeypatch.setattr(router, "_load_sessions_async", _async_return({}))
        with pytest.raises(Exception):
            await router.delete_session("nope")
        _reset_api()


# ---------------------------------------------------------------------------
# 9. push_cron_event：通知带 content，_pending_cron_info 以 message_id 为 key
# ---------------------------------------------------------------------------
class TestPushCronEvent:
    @pytest.mark.asyncio
    async def test_notification_carries_content_and_message_id_key(self, monkeypatch):
        api = _set_api({})  # session 不存在，会被 get_or_create
        monkeypatch.setattr(
            router, "_load_sessions_async",
            _async_return({"s1": {"session_id": "s1", "channel": "webui"}}),
        )
        monkeypatch.setattr(router, "update_session_activity", lambda sid: None)

        event_data = {
            "type": "cron.message",
            "payload": {
                "task_id": "t1",
                "task_name": "daily",
                "content": "say hi\n[Cron Task: daily]",
                "cron_id": "cron_1",
                "trigger_time": "09:00",
                "agent_id": "main_agent",
            },
        }
        await router.push_cron_event("s1", event_data)

        # 通知队列携带 content
        q = router._cron_sse_queues.get("s1")
        assert q is not None
        notif = q.get_nowait()
        assert notif["content"] == "say hi\n[Cron Task: daily]"
        assert notif["task_name"] == "daily"

        # _pending_cron_info 以 message_id 为 key（非 session_id）
        assert "s1" not in router._pending_cron_info
        # 推送到引擎的事件 payload.message_id 作为 pending 的 key
        pushed = [e for (sid, e) in api.pushed if sid == "s1"]
        assert len(pushed) == 1
        msg_id = pushed[0].payload["message_id"]
        assert msg_id in router._pending_cron_info
        assert router._pending_cron_info[msg_id]["task_id"] == "t1"
        _reset_api()


async def _noop(*args, **kwargs):
    return None


def _async_return(value):
    async def _inner():
        return value
    return _inner


# ---------------------------------------------------------------------------
# 6. 新 SSE 消息帧组装：_stream_message_events（message.start/end 长连接分帧）
# ---------------------------------------------------------------------------
class TestStreamMessageFraming:
    """验证重构后的消息帧组装（长连接持续分帧、补发 start/end、cron 元信息）"""

    def _ev(self, etype, payload, session_id="s1"):
        return Event(type=etype, payload=payload, session_id=session_id)

    async def _collect(self, session, feed, poll_interval=0.03):
        """先启动生成器（live 模式），再注入事件；会话停止后结束收集"""
        frames = []

        async def _feed():
            for ev in feed:
                await asyncio.sleep(poll_interval)
                session._event_buffer.append(ev)
            await asyncio.sleep(0.3)
            session.is_alive = False

        asyncio.get_running_loop().create_task(_feed())
        async for f in router._stream_message_events("s1", session, poll_interval=poll_interval):
            if f is not None:
                frames.append(f)
        return frames

    @pytest.mark.asyncio
    async def test_full_message_framing(self):
        feed = [
            self._ev("stream.thinking", {"delta": "t ", "message_id": "m1"}),
            self._ev("stream.chunk", {"delta": "He", "message_id": "m1"}),
            self._ev("stream.fragment", {
                "has_tool_calls": True,
                "tool_calls": [{"id": "c1", "function": {"name": "run_shell", "arguments": "{}"}}],
                "message_id": "m1",
            }),
            self._ev("stream.tool_result", {
                "tool_call_id": "c1", "tool_name": "run_shell", "result": "ok", "message_id": "m1",
            }),
            self._ev("stream.chunk", {"delta": "!", "message_id": "m1"}),
            self._ev("stream.end", {"message_id": "m1"}),
            self._ev("stream.chunk", {"delta": "second", "message_id": "m2"}),
            self._ev("stream.end", {"message_id": "m2"}),
        ]
        frames = await self._collect(FakeSession(), feed)
        events = [f["event"] for f in frames]
        assert events[0] == "message.start"
        assert events[1] == "message.thinking"
        assert "message.tool_start" in events and "message.tool_result" in events
        # 每条逻辑消息恰好一次 message.start；长连接持续到第二条消息
        assert events.count("message.start") == 2
        assert events[-1] == "message.end"
        assert frames[-1]["id"] == "m2"
        assert frames[0]["data"]["message_id"] == "m1"
        assert frames[0]["data"]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_pure_tool_flow_gets_start(self):
        """第一条事件就是 tool_start 的纯工具流也补发 message.start"""
        feed = [
            self._ev("stream.fragment", {
                "has_tool_calls": True,
                "tool_calls": [{"id": "c2", "function": {"name": "run_shell", "arguments": "{}"}}],
                "message_id": "m3",
            }),
            self._ev("stream.end", {"message_id": "m3"}),
        ]
        frames = await self._collect(FakeSession(), feed)
        events = [f["event"] for f in frames]
        assert events[0] == "message.start" and events[-1] == "message.end"

    @pytest.mark.asyncio
    async def test_unfinished_message_gets_end_on_session_stop(self):
        """会话停止时仍有在途消息 -> 补发 message.end 收尾"""
        feed = [self._ev("stream.chunk", {"delta": "x", "message_id": "m4"})]
        frames = await self._collect(FakeSession(), feed)
        events = [f["event"] for f in frames]
        assert events == ["message.start", "message.chunk", "message.end"]

    @pytest.mark.asyncio
    async def test_cron_meta_in_start(self):
        """cron 元信息应出现在 message.start 帧中"""
        router._pending_cron_info["m5"] = {
            "cron_id": "cr", "task_id": "t1", "task_name": "巡检", "trigger_time": "09:00",
        }
        try:
            feed = [
                self._ev("stream.chunk", {"delta": "hi", "message_id": "m5"}),
                self._ev("stream.end", {"message_id": "m5"}),
            ]
            frames = await self._collect(FakeSession(), feed)
            start = frames[0]["data"]
            assert start.get("isCron") is True
            assert start.get("taskName") == "巡检"
        finally:
            router._pending_cron_info.pop("m5", None)
