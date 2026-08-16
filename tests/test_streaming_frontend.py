# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""WebUI 流式输出前端专项测试

针对 2026-08 流式重构 + thinking 切分修复新增的专项测试：
- 后端：SSE 消息帧组装（_stream_message_events 顺序/分帧/长连接）、
  chat_stream_subscribe 会话即时创建、message.start cron 元信息
- 前端（node）：flushPendingDeltas 的 thinking 单块合并与顺序保持、
  流式消息状态机（ensureStreamingMsg 幂等 / start-end 生命周期）、
  buildHistoryMessages 多轮工具链 thinking 合并
"""

import asyncio
import json
import re
import subprocess
import time
from pathlib import Path

import pytest
from fastmind import Event
from fastmind.core.engine import EventBuffer

import gateway.router as router

WEBUI_INDEX = Path(__file__).parent.parent / "webui" / "index.html"


# ---------------------------------------------------------------------------
# 工具 & fixtures
# ---------------------------------------------------------------------------
class FakeSession:
    """最小会话对象（含 _event_buffer / is_alive）"""

    def __init__(self):
        self._event_buffer = EventBuffer(maxlen=5000)
        self.is_alive = True

    async def stop(self):
        self.is_alive = False


class FakeEngine:
    def __init__(self, sessions):
        self._sessions = sessions

    def get_or_create_session(self, session_id):
        if session_id not in self._sessions:
            self._sessions[session_id] = FakeSession()
        return self._sessions[session_id]


class FakeAPI:
    def __init__(self, sessions=None):
        self._sessions = sessions or {}
        self._engine = FakeEngine(self._sessions)

    def get_session(self, session_id):
        return self._sessions.get(session_id)


def _ev(etype, payload, sid="s1"):
    return Event(type=etype, payload=payload, session_id=sid)


@pytest.fixture(autouse=True)
def _clean_stream_state():
    router._session_stream_state.clear()
    router._session_state_cursors.clear()
    router._pending_cron_info.clear()
    yield
    router._session_stream_state.clear()
    router._session_state_cursors.clear()
    router._pending_cron_info.clear()
    router._websocket_api = None


# ---------------------------------------------------------------------------
# 1. 后端：_stream_message_events 帧组装（顺序 / 分帧 / 长连接）
# ---------------------------------------------------------------------------
class TestStreamMessageEvents:
    """SSE 消息帧组装：顺序保持、thinking 独立帧、message.start/end 分帧"""

    async def _collect(self, session, feed, poll_interval=0.02):
        """live 模式：先启动生成器，再注入事件；喂完停止会话结束收集"""
        frames = []

        async def _feed():
            for ev in feed:
                await asyncio.sleep(poll_interval)
                session._event_buffer.append(ev)
            await asyncio.sleep(0.2)
            session.is_alive = False

        asyncio.get_running_loop().create_task(_feed())
        async for f in router._stream_message_events(
            "s1", session, poll_interval=poll_interval
        ):
            if f is not None:
                frames.append(f)
        return frames

    @pytest.mark.asyncio
    async def test_thinking_chunk_order_preserved(self):
        """thinking/text/tool 交错事件：SSE 帧顺序严格保持，不重组"""
        feed = [
            _ev("stream.thinking", {"delta": "T1", "message_id": "m"}),
            _ev("stream.chunk", {"delta": "C1", "message_id": "m"}),
            _ev("stream.thinking", {"delta": "T2", "message_id": "m"}),
            _ev("stream.chunk", {"delta": "C2", "message_id": "m"}),
            _ev("stream.end", {"message_id": "m"}),
        ]
        frames = await self._collect(FakeSession(), feed)
        events = [f["event"] for f in frames]
        # message.start 只发一次，之后按原始顺序
        assert events[0] == "message.start"
        assert events[1:] == [
            "message.thinking", "message.chunk",
            "message.thinking", "message.chunk", "message.end",
        ], events
        # 所有帧 id 一致（同一条逻辑消息）
        ids = {f["id"] for f in frames}
        assert ids == {"m"}

    @pytest.mark.asyncio
    async def test_long_lived_connection_multiple_messages(self):
        """长连接连续两条消息：各自 start/end，不串帧"""
        feed = [
            _ev("stream.chunk", {"delta": "a", "message_id": "m1"}),
            _ev("stream.end", {"message_id": "m1"}),
            _ev("stream.chunk", {"delta": "b", "message_id": "m2"}),
            _ev("stream.end", {"message_id": "m2"}),
        ]
        frames = await self._collect(FakeSession(), feed)
        events = [f["event"] for f in frames]
        assert events == [
            "message.start", "message.chunk", "message.end",
            "message.start", "message.chunk", "message.end",
        ]
        assert frames[0]["id"] == "m1" and frames[3]["id"] == "m2"

    @pytest.mark.asyncio
    async def test_pure_tool_flow_frames(self):
        """纯工具流（无 thinking/chunk）：tool_start/tool_result 也有 start/end 帧"""
        feed = [
            _ev("stream.fragment", {
                "has_tool_calls": True,
                "tool_calls": [{"id": "c1", "function": {"name": "run_shell", "arguments": "{}"}}],
                "message_id": "m",
            }),
            _ev("stream.tool_result", {
                "tool_call_id": "c1", "tool_name": "run_shell", "result": "ok", "message_id": "m",
            }),
            _ev("stream.end", {"message_id": "m"}),
        ]
        frames = await self._collect(FakeSession(), feed)
        events = [f["event"] for f in frames]
        assert events == [
            "message.start", "message.tool_start",
            "message.tool_result", "message.end",
        ]
        # tool_start 帧数据包含完整 tool_calls
        ts = frames[1]["data"]
        assert len(ts["tool_calls"]) == 1
        assert ts["tool_calls"][0]["function"]["name"] == "run_shell"

    @pytest.mark.asyncio
    async def test_json_serializable_frames(self):
        """所有帧 data 均可 JSON 序列化（SSE 输出契约）"""
        feed = [
            _ev("stream.thinking", {"delta": "t", "message_id": "m"}),
            _ev("stream.chunk", {"delta": "c", "message_id": "m"}),
            _ev("stream.end", {"message_id": "m"}),
        ]
        frames = await self._collect(FakeSession(), feed)
        for f in frames:
            json.dumps(f["data"])  # 不抛异常即通过


# ---------------------------------------------------------------------------
# 2. 后端：chat_stream_subscribe 会话即时创建（消除 60s 等待窗口）
# ---------------------------------------------------------------------------
class TestChatStreamSubscribeEagerSession:
    """连接时会话不存在 → 主动 get_or_create_session，不等 60s"""

    async def _read_first(self, session_id, poll=None, max_chunks=8):
        """直接驱动 StreamingResponse.body_iterator；poll() 返回 True 或达上限后关闭"""
        resp = await router.chat_stream_subscribe(session_id)
        chunks = []
        try:
            async for chunk in resp.body_iterator:
                chunks.append(chunk)
                if poll is not None and poll():
                    break
                if len(chunks) >= max_chunks:
                    break
        finally:
            await resp.body_iterator.aclose()
        return "".join(chunks)

    @pytest.mark.asyncio
    async def test_eager_session_creation(self):
        """连接时会话不存在 → 主动创建，且首个事件为 connected"""
        fake_api = FakeAPI()
        router._websocket_api = fake_api
        sid = "fresh_session_eager_test"
        assert sid not in fake_api._sessions

        text = await self._read_first(sid, poll=lambda: sid in fake_api._sessions)

        assert "event: connected" in text
        assert sid in fake_api._sessions, "连接后会话应被主动创建"

    @pytest.mark.asyncio
    async def test_existing_session_reused(self):
        """会话已存在时直接复用，不重复创建"""
        fake_api = FakeAPI()
        router._websocket_api = fake_api
        sid = "existing_session"
        session = FakeSession()
        fake_api._sessions[sid] = session

        await self._read_first(sid, poll=lambda: sid in fake_api._sessions)

        assert fake_api._sessions[sid] is session

    @pytest.mark.asyncio
    async def test_api_not_initialized_raises_500(self):
        """_websocket_api 未初始化时返回 500（HTTPException）"""
        router._websocket_api = None
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await router.chat_stream_subscribe("any_sid")
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# 3. 后端：_build_stream_start_data cron 元信息
# ---------------------------------------------------------------------------
class TestBuildStreamStartData:
    def test_plain_assistant_start_data(self):
        data = router._build_stream_start_data("s1", "msg_1")
        assert data["role"] == "assistant"
        assert data["message_id"] == "msg_1"
        assert "timestamp" in data
        assert "isCron" not in data

    def test_cron_meta_attached(self):
        router._pending_cron_info["msg_cron"] = {
            "cron_id": "cr1", "task_id": "t1", "task_name": "每日巡检",
            "trigger_time": "09:00",
        }
        data = router._build_stream_start_data("s1", "msg_cron")
        assert data["isCron"] is True
        assert data["taskName"] == "每日巡检"
        assert data["taskId"] == "t1"
        assert data["triggerTime"] == "09:00"

    def test_cron_meta_peek_not_pop(self):
        """message.start 只 peek 不 pop，累积器仍可消费"""
        router._pending_cron_info["m"] = {"cron_id": "c", "task_id": "t", "task_name": "n"}
        router._build_stream_start_data("s1", "m")
        assert "m" in router._pending_cron_info  # 未被移除


# ---------------------------------------------------------------------------
# 4. 前端（node）：thinking 合并 / 顺序保持 / 流式状态机
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def frontend_funcs():
    """提取 index.html 中流式相关纯函数（newAssistantMessage..loadSessions 之间）"""
    if not subprocess.run(["which", "node"], capture_output=True).returncode == 0:
        pytest.skip("node 不可用")
    src = WEBUI_INDEX.read_text(encoding="utf-8")
    scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", src, re.S)
    body = scripts[-1]
    start = body.index("function newAssistantMessage")
    # 终点取 connect() 之前：覆盖 ensureStreamingMsg / handleStream* 流式状态机函数
    end = body.index("function connect(sessionId, cursor)")
    funcs = body[start:end]
    funcs = funcs.replace("return reactive(raw);", "return raw;")
    return funcs


def _run_frontend(funcs, probe, stubs=""):
    """在 node 中运行前端逻辑（stub 浏览器/Vue API）"""
    runner = f"""
const reactive = (x) => x;
const messages = {{ value: [] }};
const isStreaming = {{ value: false }};
const isSending = {{ value: false }};
const sessions = {{ value: [] }};
const currentSessionId = {{ value: 's1' }};
const streamingMsgById = new Map();
const shouldAutoScroll = {{ value: true }};
let nextTick = (fn) => {{ if (typeof fn === 'function') fn(); return Promise.resolve(); }};
let requestAnimationFrame = (fn) => {{ fn(); return 1; }};
let cancelAnimationFrame = () => {{}};
const document = {{ querySelector: () => null, querySelectorAll: () => [] }};
function scrollBottom() {{}}
function loadSessions() {{}}
function loadUnreadCounts() {{}}
{stubs}
{funcs}
{probe}
"""
    r = subprocess.run(["node", "-e", runner], capture_output=True, text=True)
    assert r.returncode == 0, f"node 执行失败: {r.stderr[:600]}"
    return r.stdout.strip().splitlines()[-1]


class TestFrontendThinkingMerge:
    """flushPendingDeltas：thinking 合并单块、置顶、顺序保持（本次修复核心）"""

    def test_thinking_single_block_across_react_cycles(self, frontend_funcs):
        probe = r"""
const msg = newAssistantMessage('m1');
// ReAct 循环：思考→文本→工具→思考→文本（thinking 交错）
flushPendingDeltas(); // 空
pendingDeltas.push({ msg, type: 'thinking', delta: '第一段' });
pendingDeltas.push({ msg, type: 'text', delta: '你好' });
// 工具块（直接插入，模拟 handleStreamToolStart）
ensureToolCallBlock(msg, { id: 'c1', function: { name: 'run_shell', arguments: '{"command":"ls"}' } });
pendingDeltas.push({ msg, type: 'thinking', delta: '第二段' });
pendingDeltas.push({ msg, type: 'text', delta: '世界' });
flushPendingDeltas();
const out = {
  types: msg.blocks.map(b => b.type),
  thinkCount: msg.blocks.filter(b => b.type === 'thinking').length,
  thinkText: (msg.blocks.find(b => b.type === 'thinking') || {}).text || '',
  firstIsThinking: msg.blocks[0].type === 'thinking',
  textCount: msg.blocks.filter(b => b.type === 'text').length,
  textText: (msg.blocks.find(b => b.type === 'text') || {}).text || '',
};
console.log(JSON.stringify(out));
"""
        out = json.loads(_run_frontend(frontend_funcs, probe))
        assert out["thinkCount"] == 1, "thinking 被切分"
        assert out["thinkText"] == "第一段第二段", out
        assert out["firstIsThinking"], "thinking 未置顶"
        assert out["textText"] == "你好世界"
        # thinking 块位于工具块之前
        assert out["types"].index("thinking") < out["types"].index("tool_call")

    def test_delta_arrival_order_preserved(self, frontend_funcs):
        """同一批内 thinking/text 交错：按到达顺序处理，thinking 仍在文本前"""
        probe = r"""
const msg = newAssistantMessage('m2');
pendingDeltas.push({ msg, type: 'text', delta: '先文本' });
pendingDeltas.push({ msg, type: 'thinking', delta: '后思考' });
flushPendingDeltas();
const out = {
  types: msg.blocks.map(b => b.type),
  thinkText: (msg.blocks.find(b => b.type === 'thinking') || {}).text || '',
  textText: (msg.blocks.find(b => b.type === 'text') || {}).text || '',
};
console.log(JSON.stringify(out));
"""
        out = json.loads(_run_frontend(frontend_funcs, probe))
        # thinking 独立块且内容完整，位于最前
        assert out["thinkText"] == "后思考"
        assert out["textText"] == "先文本"
        assert out["types"][0] == "thinking"


class TestFrontendStreamStateMachine:
    """ensureStreamingMsg / handleStreamStart / handleStreamEnd 状态机"""

    def test_ensure_streaming_msg_idempotent(self, frontend_funcs):
        probe = r"""
const m1 = ensureStreamingMsg('msg-x', 'chunk');
const m2 = ensureStreamingMsg('msg-x', 'chunk');
const out = {
  same: m1 === m2,
  inMessages: messages.value.includes(m1),
  pushCount: messages.value.length,
  streaming: isStreaming.value,
};
console.log(JSON.stringify(out));
"""
        out = json.loads(_run_frontend(frontend_funcs, probe))
        assert out["same"] is True, "同一 msgId 应返回同一消息"
        assert out["pushCount"] == 1, "不应重复 push"
        assert out["streaming"] is True

    def test_start_end_lifecycle(self, frontend_funcs):
        probe = r"""
handleStreamStart({ role: 'assistant', timestamp: 1, message_id: 'life-1' }, 'life-1');
const during = {
  has: streamingMsgById.has('life-1'),
  isStreaming: isStreaming.value,
  isSending: isSending.value,
  msgs: messages.value.length,
};
queueTextDelta(streamingMsgById.get('life-1'), 'hi');
flushPendingDeltas();
handleStreamEnd('life-1');
const after = {
  has: streamingMsgById.has('life-1'),
  isStreaming: isStreaming.value,
  streamingFlag: (messages.value[0] || {})._isStreaming,
  text: (messages.value[0] && messages.value[0].blocks[0]) ? messages.value[0].blocks[0].text : '',
};
console.log(JSON.stringify({ during, after }));
"""
        out = json.loads(_run_frontend(frontend_funcs, probe))
        assert out["during"]["has"] is True
        assert out["during"]["isStreaming"] is True
        assert out["during"]["isSending"] is False
        assert out["after"]["has"] is False, "end 后应清理 streamingMsgById"
        assert out["after"]["isStreaming"] is False
        assert out["after"]["streamingFlag"] is False, "消息应被 settle"
        assert out["after"]["text"] == "hi"

    def test_start_duplicate_frame_idempotent(self, frontend_funcs):
        """断线续传重复 message.start 帧：幂等，不重复建消息"""
        probe = r"""
handleStreamStart({ message_id: 'dup' }, 'dup');
handleStreamStart({ message_id: 'dup' }, 'dup');
console.log(JSON.stringify({ count: messages.value.length, has: streamingMsgById.has('dup') }));
"""
        out = json.loads(_run_frontend(frontend_funcs, probe))
        assert out["count"] == 1
        assert out["has"] is True


class TestFrontendHistoryThinkingMerge:
    """buildHistoryMessages：多轮工具链 thinking 合并为单块"""

    def test_multi_tool_chain_thinking_merged(self, frontend_funcs):
        probe = r"""
const history = [
  { role: 'user', content: 'q', timestamp: 1 },
  { role: 'assistant', content: '', reasoning_content: 'r1', tool_calls: [
      { id: 'a1', type: 'function', function: { name: 'run_shell', arguments: '{"cmd":"1"}' } }], timestamp: 2 },
  { role: 'tool', tool_call_id: 'a1', content: '[run_shell]: out1', timestamp: 3 },
  { role: 'assistant', content: '', reasoning_content: 'r2', tool_calls: [
      { id: 'a2', type: 'function', function: { name: 'run_skills', arguments: '{"name":"x"}' } }], timestamp: 4 },
  { role: 'tool', tool_call_id: 'a2', content: '[run_skills]: out2', timestamp: 5 },
  { role: 'assistant', content: '最终回答', reasoning_content: 'r3', timestamp: 6 },
];
const turns = buildHistoryMessages(history);
const b = turns[1].blocks;
console.log(JSON.stringify({
  turnCount: turns.length,
  types: b.map(x => x.type),
  thinkCount: b.filter(x => x.type === 'thinking').length,
  thinkText: (b.find(x => x.type === 'thinking') || {}).text,
  lastType: b[b.length - 1].type,
}));
"""
        out = json.loads(_run_frontend(frontend_funcs, probe))
        assert out["turnCount"] == 2
        # 三段推理合并为单块，置顶
        assert out["thinkCount"] == 1, "多轮工具链 thinking 被切分"
        assert out["thinkText"] == "r1\n\nr2\n\nr3", out
        assert out["types"][0] == "thinking"
        assert out["lastType"] == "text"
