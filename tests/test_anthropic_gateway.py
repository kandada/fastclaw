# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""Anthropic 网关专项测试

覆盖 app.py 新增的 anthropic 网关：
- _get_llm_client：按 gateway 分支创建客户端 + base_url /v1 规范化 + 缓存
- _to_anthropic_messages / _to_anthropic_tools：OpenAI → Anthropic 格式转换
- _stream_anthropic_response：流式事件解析（thinking/text/tool_use/signature）
- fastclaw_agent：gateway=anthropic 时端到端（含 ReAct 多轮工具链、消息落盘格式）
"""

import asyncio
import importlib
import json
from types import SimpleNamespace

import pytest
from anthropic import AsyncAnthropic
from fastmind import Event
from openai import AsyncOpenAI

app_mod = importlib.import_module("core.app")


# ---------------------------------------------------------------------------
# Mock（Anthropic 流事件 / 客户端）
# ---------------------------------------------------------------------------
def _ev(name, **kw):
    return SimpleNamespace(type=name, **kw)


def thinking_delta(text="", signature=None):
    return _ev(
        "content_block_delta",
        index=0,
        delta=SimpleNamespace(
            type="thinking_delta", thinking=text, signature=signature,
            text=None, partial_json=None,
        ),
    )


def text_delta(text):
    return _ev(
        "content_block_delta",
        index=0,
        delta=SimpleNamespace(
            type="text_delta", text=text, thinking=None, signature=None, partial_json=None
        ),
    )


def tool_start(index, tc_id, name):
    return _ev(
        "content_block_start",
        index=index,
        content_block=SimpleNamespace(type="tool_use", id=tc_id, name=name, input={}),
    )


def json_delta(index, partial):
    return _ev(
        "content_block_delta",
        index=index,
        delta=SimpleNamespace(
            type="input_json_delta", partial_json=partial,
            text=None, thinking=None, signature=None,
        ),
    )


def block_stop(index=0):
    return _ev("content_block_stop", index=index)


class FakeAnthropicStream:
    def __init__(self, events):
        self._it = iter(events)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class FakeAnthropicMessages:
    def __init__(self, events=None, error=None):
        self.events = events or []
        self.error = error
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return FakeAnthropicStream(self.events)


class FakeAnthropicClient:
    def __init__(self, events=None, error=None):
        self.messages = FakeAnthropicMessages(events, error)


class MockQueue:
    def __init__(self):
        self.events = []

    def put_nowait(self, event):
        self.events.append(event)


async def _noop(*args, **kwargs):
    return None


def _make_state(session_id="s1", messages=None, gateway="anthropic", enable_thinking=False):
    return {
        "_session_id": session_id,
        "_output_queue": MockQueue(),
        "_agent_config": {
            "llm": {
                "gateway": gateway,
                "model": "claude-3-5-sonnet-20241022",
                "enable_thinking": enable_thinking,
            },
            "context": {},
        },
        "_personality": "",
        "messages": messages if messages is not None else [],
    }


@pytest.fixture(autouse=True)
def _clean_client_cache():
    app_mod._LLM_CLIENT_CACHE.clear()
    app_mod._ANTHROPIC_THINKING_MODE_CACHE.clear()
    yield
    app_mod._LLM_CLIENT_CACHE.clear()
    app_mod._ANTHROPIC_THINKING_MODE_CACHE.clear()


@pytest.fixture(autouse=True)
def _mock_save(monkeypatch):
    monkeypatch.setattr(app_mod, "_save_messages_async", _noop)
    # fastclaw_agent 内会按 load_session_agent_id 决定是否重载 agent 配置，
    # 测试会话绑定真实 agent（如 MiniMax-M2.7）会覆盖我们注入的 anthropic 配置，故置空。
    monkeypatch.setattr(app_mod, "load_session_agent_id", lambda sid: "")


# ---------------------------------------------------------------------------
# 1. _get_llm_client：gateway 分支 + base_url 规范化 + 缓存
# ---------------------------------------------------------------------------
class TestGetLLMClientGateway:
    def test_anthropic_creates_async_anthropic(self):
        client = app_mod._get_llm_client(
            {"gateway": "anthropic", "api_key": "k", "base_url": "https://api.anthropic.com"}
        )
        assert isinstance(client, AsyncAnthropic)

    def test_anthropic_strips_trailing_v1(self):
        """真 Anthropic：SDK 内部拼 /v1/messages，用户多写 /v1 需去除，避免 /v1/v1"""
        client = app_mod._get_llm_client(
            {"gateway": "anthropic", "api_key": "k", "base_url": "https://api.anthropic.com/v1"}
        )
        assert str(client.base_url) == "https://api.anthropic.com"
        client2 = app_mod._get_llm_client(
            {"gateway": "anthropic", "api_key": "k", "base_url": "https://proxy.example.com/v1/"}
        )
        assert str(client2.base_url) == "https://proxy.example.com"

    def test_minimax_base_url_adjusted_to_anthropic(self):
        """MiniMax：OpenAI 风格 .../v1 自动调整为 .../anthropic 兼容端点"""
        client = app_mod._get_llm_client(
            {"gateway": "anthropic", "api_key": "k", "base_url": "https://api.minimax.chat/v1"}
        )
        assert str(client.base_url).rstrip("/") == "https://api.minimax.chat/anthropic"

    def test_moonshot_deepseek_base_url_adjusted(self):
        """Moonshot / DeepSeek 同样转换为 .../anthropic 端点"""
        c1 = app_mod._get_llm_client(
            {"gateway": "anthropic", "api_key": "k", "base_url": "https://api.moonshot.cn/v1"}
        )
        assert str(c1.base_url).rstrip("/") == "https://api.moonshot.cn/anthropic"
        c2 = app_mod._get_llm_client(
            {"gateway": "anthropic", "api_key": "k", "base_url": "https://api.deepseek.com/v1"}
        )
        assert str(c2.base_url).rstrip("/") == "https://api.deepseek.com/anthropic"

    def test_already_anthropic_suffix_unchanged(self):
        """已是 .../anthropic 结尾则不重复拼接"""
        client = app_mod._get_llm_client(
            {"gateway": "anthropic", "api_key": "k", "base_url": "https://api.minimax.chat/anthropic"}
        )
        assert str(client.base_url).rstrip("/") == "https://api.minimax.chat/anthropic"

    def test_adjust_anthropic_base_url_helper(self):
        assert app_mod._adjust_anthropic_base_url("") == ""
        assert app_mod._adjust_anthropic_base_url("https://api.minimax.chat/v1/anthropic") == (
            "https://api.minimax.chat/anthropic"
        )
        assert app_mod._adjust_anthropic_base_url("https://api.anthropic.com/v1") == (
            "https://api.anthropic.com"
        )

    def test_openai_default_gateway(self):
        client = app_mod._get_llm_client({"api_key": "k"})
        assert isinstance(client, AsyncOpenAI)

    def test_openai_explicit_gateway(self):
        client = app_mod._get_llm_client({"gateway": "openai", "api_key": "k"})
        assert isinstance(client, AsyncOpenAI)
        assert str(client.base_url).rstrip("/") == "https://api.deepseek.com/v1"

    def test_cache_isolated_by_gateway(self):
        c1 = app_mod._get_llm_client({"gateway": "openai", "api_key": "k"})
        c2 = app_mod._get_llm_client({"gateway": "anthropic", "api_key": "k"})
        assert c1 is not c2, "不同 gateway 不应共用缓存"
        c3 = app_mod._get_llm_client({"gateway": "anthropic", "api_key": "k"})
        assert c2 is c3, "相同 gateway/凭据应命中缓存"


# ---------------------------------------------------------------------------
# 2. 消息 / 工具 schema 转换
# ---------------------------------------------------------------------------
class TestToAnthropicMessages:
    def test_user_message(self):
        out = app_mod._to_anthropic_messages([{"role": "user", "content": "hi"}])
        assert out == [{"role": "user", "content": "hi"}]

    def test_assistant_with_thinking_content_tool_calls(self):
        msgs = [
            {
                "role": "assistant",
                "content": "结果在这",
                "reasoning_content": "推理",
                "thinking_signature": "sig-abc",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "run_shell", "arguments": '{"command": "ls"}'},
                    }
                ],
            }
        ]
        out = app_mod._to_anthropic_messages(msgs)
        assert len(out) == 1
        content = out[0]["content"]
        # thinking 块带 signature，位于 text 前，tool_use 在后
        assert content == [
            {"type": "thinking", "thinking": "推理", "signature": "sig-abc"},
            {"type": "text", "text": "结果在这"},
            {"type": "tool_use", "id": "c1", "name": "run_shell", "input": {"command": "ls"}},
        ]

    def test_assistant_without_reasoning(self):
        out = app_mod._to_anthropic_messages([{"role": "assistant", "content": "ok"}])
        assert out[0]["content"] == [{"type": "text", "text": "ok"}]

    def test_tool_message_becomes_user_tool_result(self):
        out = app_mod._to_anthropic_messages(
            [{"role": "tool", "tool_call_id": "c1", "content": "out1"}]
        )
        assert out == [
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "out1"}],
            }
        ]

    def test_system_message_skipped(self):
        out = app_mod._to_anthropic_messages([{"role": "system", "content": "sys"}])
        assert out == []

    def test_invalid_tool_arguments_fallback(self):
        msgs = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "c1", "type": "function",
                     "function": {"name": "run_shell", "arguments": "not json"}}
                ],
            }
        ]
        out = app_mod._to_anthropic_messages(msgs)
        assert out[0]["content"][0]["input"] == {}


class TestToAnthropicTools:
    def test_openai_schema_with_function_wrapper(self):
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "run_shell",
                    "description": "Run shell",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        out = app_mod._to_anthropic_tools(schemas)
        assert out == [
            {
                "name": "run_shell",
                "description": "Run shell",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]

    def test_flat_schema(self):
        schemas = [{"name": "run_skills", "description": "Skills", "parameters": {}}]
        out = app_mod._to_anthropic_tools(schemas)
        assert out[0]["name"] == "run_skills"

    def test_empty_schema(self):
        assert app_mod._to_anthropic_tools([]) == []
        assert app_mod._to_anthropic_tools(None) == []


# ---------------------------------------------------------------------------
# 3. _stream_anthropic_response：流式解析
# ---------------------------------------------------------------------------
class TestStreamAnthropic:
    def _run(self, events, llm_config=None, messages=None, tool_schemas=None):
        cfg = dict(
            gateway="anthropic", model="claude-3-5-sonnet-20241022", api_key="k"
        )
        if llm_config:
            cfg.update(llm_config)
        fake = FakeAnthropicClient(events=events)
        q = MockQueue()
        app_mod._get_llm_client = lambda _c: fake
        result = asyncio.run(
            app_mod._stream_anthropic_response(
                llm_config=cfg,
                llm_messages=messages or [{"role": "user", "content": "hi"}],
                tool_schemas=tool_schemas or [],
                system_prompt="SYSTEM",
                msg_id="m1",
                session_id="s1",
                output_queue=q,
                stream_chunk_timeout=5,
            )
        )
        return result, q, fake

    def test_text_streaming(self):
        (content, reasoning, tool_calls, has_tools, sig), q, _ = self._run(
            [text_delta("你"), text_delta("好")]
        )
        assert content == "你好"
        assert reasoning == ""
        assert has_tools is False
        assert tool_calls == []
        assert sig == ""
        chunk_events = [e for e in q.events if e.type == "stream.chunk"]
        assert [e.payload["delta"] for e in chunk_events] == ["你", "好"]
        assert all(e.payload["message_id"] == "m1" for e in q.events)

    def test_thinking_streaming_and_signature(self):
        events = [thinking_delta("思考中", None), thinking_delta("", "sig-123"), text_delta("ok")]
        (content, reasoning, tool_calls, has_tools, sig), q, _ = self._run(events)
        assert reasoning == "思考中"
        assert sig == "sig-123"
        assert content == "ok"
        thinking_events = [e for e in q.events if e.type == "stream.thinking"]
        assert [e.payload["delta"] for e in thinking_events] == ["思考中"]

    def test_tool_use_streaming(self):
        events = [
            tool_start(0, "c1", "run_shell"),
            json_delta(0, '{"command":'),
            json_delta(0, '"ls"}'),
            block_stop(0),
        ]
        (content, reasoning, tool_calls, has_tools, sig), q, _ = self._run(events)
        assert has_tools is True
        assert content == ""
        assert tool_calls == [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "run_shell", "arguments": '{"command":"ls"}'},
            }
        ]

    def test_request_kwargs(self):
        _, _, fake = self._run(
            [text_delta("ok")],
            llm_config={"anthropic_max_tokens": 2048},
        )
        kwargs = fake.messages.calls[0]
        assert kwargs["model"] == "claude-3-5-sonnet-20241022"
        assert kwargs["max_tokens"] == 2048
        assert kwargs["system"] == "SYSTEM"
        assert kwargs["stream"] is True
        assert kwargs["messages"] == [{"role": "user", "content": "hi"}]

    def test_thinking_adaptive_by_default(self):
        """默认优先尝试 adaptive 模式（Claude 4.6+ / MiniMax 兼容）"""
        _, _, fake = self._run([text_delta("ok")])
        kwargs = fake.messages.calls[0]
        assert kwargs["thinking"] == {"type": "adaptive"}

    def test_thinking_disabled_forces_none(self):
        """enable_thinking=False：不附加 thinking 参数"""
        _, _, fake = self._run(
            [text_delta("ok")], llm_config={"enable_thinking": False}
        )
        kwargs = fake.messages.calls[0]
        assert "thinking" not in kwargs

    def test_thinking_enabled_uses_budget_on_enabled_fallback(self):
        """enable_thinking=True 且 enabled 模式时使用 thinking_budget_tokens"""
        budget = {"type": "enabled", "budget_tokens": 4000}
        assert app_mod.thinking_kwargs_for_mode("enabled", 4000) == budget

    def test_thinking_mode_state_machine_degrades_on_rejection(self):
        """adaptive 被拒 → 自动降级 enabled（带 budget）重试成功"""
        events = [thinking_delta("想", None), text_delta("答")]
        fake = FakeAnthropicClient(events=events)
        fake.messages.calls = []
        orig_create = fake.messages.create

        async def flaky_create(**kwargs):
            fake.messages.calls.append(kwargs)
            if kwargs.get("thinking") == {"type": "adaptive"}:
                raise RuntimeError('"thinking.type.adaptive" is not supported')
            return FakeAnthropicStream(events)

        fake.messages.create = flaky_create
        app_mod._get_llm_client = lambda _c: fake
        q = MockQueue()
        result = asyncio.run(app_mod._stream_anthropic_response(
            llm_config={"gateway": "anthropic", "model": "m-adapt", "api_key": "k"},
            llm_messages=[{"role": "user", "content": "hi"}],
            tool_schemas=[],
            system_prompt="S",
            msg_id="m1",
            session_id="s1",
            output_queue=q,
            stream_chunk_timeout=5,
        ))
        content, reasoning, tool_calls, has_tools, sig = result
        assert reasoning == "想"
        assert content == "答"
        # 第一次 adaptive，第二次降级为 enabled
        modes = [c.get("thinking") for c in fake.messages.calls]
        assert modes[0] == {"type": "adaptive"}
        assert modes[1]["type"] == "enabled"
        assert modes[1]["budget_tokens"] == app_mod.DEFAULT_BUDGET_TOKENS
        # 成功模式已缓存，第二次调用不再重试降级
        assert app_mod._ANTHROPIC_THINKING_MODE_CACHE.get("m-adapt") == "enabled"

    def test_thinking_mode_full_degrade_to_none(self):
        """adaptive 与 enabled 都被拒 → 最终不带 thinking 成功"""
        events = [text_delta("ok")]
        fake = FakeAnthropicClient(events=events)

        async def flaky_create(**kwargs):
            t = kwargs.get("thinking")
            if t is not None:
                raise RuntimeError("unknown field: thinking")
            return FakeAnthropicStream(events)

        fake.messages.create = flaky_create
        app_mod._get_llm_client = lambda _c: fake
        q = MockQueue()
        asyncio.run(app_mod._stream_anthropic_response(
            llm_config={"gateway": "anthropic", "model": "m-none", "api_key": "k"},
            llm_messages=[{"role": "user", "content": "hi"}],
            tool_schemas=[],
            system_prompt="S",
            msg_id="m1",
            session_id="s1",
            output_queue=q,
            stream_chunk_timeout=5,
        ))
        assert app_mod._ANTHROPIC_THINKING_MODE_CACHE.get("m-none") == "none"

    def test_non_thinking_error_not_swallowed(self):
        """认证/配额等错误不应被当作 thinking 拒绝而误降级"""
        fake = FakeAnthropicClient(error=RuntimeError("authentication_error"))
        app_mod._get_llm_client = lambda _c: fake
        q = MockQueue()
        with pytest.raises(RuntimeError):
            asyncio.run(app_mod._stream_anthropic_response(
                llm_config={"gateway": "anthropic", "model": "m-auth", "api_key": "k"},
                llm_messages=[{"role": "user", "content": "hi"}],
                tool_schemas=[],
                system_prompt="S",
                msg_id="m1",
                session_id="s1",
                output_queue=q,
                stream_chunk_timeout=5,
            ))
        assert app_mod._ANTHROPIC_THINKING_MODE_CACHE.get("m-auth") is None

    def test_tools_converted_to_anthropic_format(self):
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "run_shell",
                    "description": "Run shell",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        _, _, fake = self._run([text_delta("ok")], tool_schemas=schemas)
        kwargs = fake.messages.calls[0]
        assert kwargs["tools"] == [
            {
                "name": "run_shell",
                "description": "Run shell",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]

    def test_tool_result_in_react_history_converted(self):
        messages = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "先看看", "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "run_shell", "arguments": '{"command":"ls"}'}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "out1"},
        ]
        _, _, fake = self._run([text_delta("完成")], messages=messages)
        anth = fake.messages.calls[0]["messages"]
        assert len(anth) == 3
        assert anth[2] == {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "out1"}],
        }


# ---------------------------------------------------------------------------
# 3.5 OpenAI 网关 thinking 兼容（MiniMax / Qwen 等非 reasoning_content 格式）
# ---------------------------------------------------------------------------
class _ODelta:
    def __init__(self, **kw):
        self.content = kw.get("content")
        self.reasoning_content = kw.get("reasoning_content")
        self.thinking = kw.get("thinking")
        self.tool_calls = kw.get("tool_calls")


class _OStream:
    def __init__(self, deltas):
        self._it = iter(deltas)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _OCompletions:
    def __init__(self, deltas):
        self._deltas = deltas

    async def create(self, **kw):
        return _OStream(self._deltas)


class _OClient:
    def __init__(self, deltas):
        self.chat = SimpleNamespace(completions=_OCompletions(deltas))


def _ochunk(delta):
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


class TestOpenAIThinkingCompatibility:
    """_stream_openai_response：统一 thinking 提取（reasoning_content / thinking / <think>）"""

    def _run(self, deltas):
        q = MockQueue()
        app_mod._get_llm_client = lambda cfg: _OClient(deltas)
        result = asyncio.run(app_mod._stream_openai_response(
            llm_config={"gateway": "openai", "model": "m"},
            llm_messages=[{"role": "user", "content": "hi"}],
            tool_schemas=[],
            system_prompt="S",
            msg_id="m1",
            session_id="s1",
            output_queue=q,
            stream_chunk_timeout=5,
        ))
        return result, q

    def test_thinking_field_recognized(self):
        """delta.thinking 字段（MiniMax 系私有协议）被识别为 thinking"""
        result, q = self._run([
            _ochunk(_ODelta(thinking="推理A")),
            _ochunk(_ODelta(thinking="推理B", content="正文")),
        ])
        content, reasoning, _, _, _ = result
        assert reasoning == "推理A推理B"
        assert content == "正文"
        assert any(e.type == "stream.thinking" for e in q.events)

    def test_reasoning_content_field(self):
        """delta.reasoning_content（DeepSeek/Kimi 风格）"""
        result, _ = self._run([
            _ochunk(_ODelta(reasoning_content="r1", content="c1")),
        ])
        content, reasoning, _, _, _ = result
        assert reasoning == "r1"
        assert content == "c1"

    def test_think_tags_in_content(self):
        """<think>...</think> 标签从 content 中剥离"""
        result, _ = self._run([
            _ochunk(_ODelta(content="<think>我要")),
            _ochunk(_ODelta(content="思考</think>正文")),
        ])
        content, reasoning, _, _, _ = result
        assert reasoning == "我要思考"
        assert content == "正文"

    def test_think_tags_split_across_chunks(self):
        """跨 chunk 切分（标签边界对齐）的 <think> 标签仍能识别"""
        result, _ = self._run([
            _ochunk(_ODelta(content="<th")),
            _ochunk(_ODelta(content="ink>思")),
            _ochunk(_ODelta(content="考</th")),
            _ochunk(_ODelta(content="ink>后")),
        ])
        content, reasoning, _, _, _ = result
        assert reasoning == "思考"
        assert content == "后"

    def test_thinking_not_mixed_with_tool_calls(self):
        """字段式 thinking 与工具调用并存：thinking 正常提取、工具调用不受影响"""
        result, _ = self._run([
            _ochunk(_ODelta(thinking="计划")),
            _ochunk(_ODelta(
                content="",
                tool_calls=[SimpleNamespace(
                    index=0, id="c1", function=SimpleNamespace(name="run_shell", arguments='{"command":"ls"}')
                )],
            )),
        ])
        content, reasoning, tool_calls, has_tools, _ = result
        assert reasoning == "计划"
        assert has_tools is True
        assert tool_calls[0]["function"]["name"] == "run_shell"


# ---------------------------------------------------------------------------
# 4. fastclaw_agent 端到端（gateway=anthropic）
# ---------------------------------------------------------------------------
class TestFastclawAgentAnthropic:
    def _run_agent(self, state, text, msg_id, fake_client):
        app_mod._get_llm_client = lambda _c: fake_client
        asyncio.run(
            app_mod.fastclaw_agent(
                state, Event("user.message", {"text": text, "message_id": msg_id}, "s1")
            )
        )

    def test_tool_round_saves_openai_schema_and_fragment(self):
        events = [
            thinking_delta("思考中", None),
            thinking_delta("", "sig-123"),
            text_delta("先看看"),
            tool_start(0, "c1", "run_shell"),
            json_delta(0, '{"command":'),
            json_delta(0, '"ls"}'),
            block_stop(0),
        ]
        state = _make_state(enable_thinking=True)
        fake = FakeAnthropicClient(events=events)
        self._run_agent(state, "ls", "m1", fake)

        q = state["_output_queue"]
        assert [e.type for e in q.events if e.type == "stream.fragment"]
        fragment = [e for e in q.events if e.type == "stream.fragment"][0]
        assert fragment.payload["has_tool_calls"] is True
        assert fragment.payload["tool_calls"][0]["function"]["name"] == "run_shell"
        assert fragment.payload["message_id"] == "m1"

        # 落盘消息保持 OpenAI 风格 schema（前端回看不依赖 anthropic 专有格式）
        asst = [m for m in state["messages"] if m.get("role") == "assistant"][-1]
        assert asst["content"] == "先看看"
        assert asst["reasoning_content"] == "思考中"
        assert asst["thinking_signature"] == "sig-123"
        assert asst["tool_calls"][0]["function"]["arguments"] == '{"command":"ls"}'
        assert state["tool_calls"][0]["id"] == "c1"

    def test_react_second_round_answer(self):
        """工具执行后再次调用：历史 tool 消息转为 tool_result 回传，最终得到回答"""
        state = _make_state()
        call1_events = [
            tool_start(0, "c1", "run_shell"),
            json_delta(0, '{"command":"ls"}'),
            block_stop(0),
        ]
        fake = FakeAnthropicClient(events=call1_events)
        self._run_agent(state, "列目录", "m1", fake)

        # 模拟 ToolNode 执行结果写回 state
        state["tool_results"] = [
            {"tool_call_id": "c1", "tool_name": "run_shell", "result": "file1\nfile2"}
        ]
        state["tool_calls"] = [
            {"id": "c1", "type": "function",
             "function": {"name": "run_shell", "arguments": '{"command":"ls"}'}}
        ]

        fake.messages = FakeAnthropicMessages(events=[thinking_delta("思考2"), text_delta("完成")])
        self._run_agent(state, "列目录", "m1", fake)

        # 第二次请求：历史中的 tool 消息应转换为 tool_result 用户消息
        anth = fake.messages.calls[0]["messages"]
        tool_result_msg = [m for m in anth if any(
            isinstance(b, dict) and b.get("type") == "tool_result"
            for b in (m.get("content") if isinstance(m.get("content"), list) else [])
        )]
        assert len(tool_result_msg) == 1
        assert tool_result_msg[0]["content"][0]["tool_use_id"] == "c1"
        assert tool_result_msg[0]["content"][0]["content"] == "file1\nfile2"

        msgs = state["messages"]
        assert msgs[-1]["role"] == "assistant"
        assert msgs[-1]["content"] == "完成"
        # 消息序列：user → assistant(tool_calls) → tool → assistant(回答)
        assert [m["role"] for m in msgs] == ["user", "assistant", "tool", "assistant"]
        # 最终回答不触发 fragment，发出 stream.end
        q = state["_output_queue"]
        assert q.events[-1].type == "stream.end"

    def test_error_emits_stream_error(self):
        state = _make_state()
        fake = FakeAnthropicClient(error=RuntimeError("anthropic boom"))
        self._run_agent(state, "hi", "m_err", fake)
        q = state["_output_queue"]
        err = [e for e in q.events if e.type == "stream.error"]
        assert err, "应发出 stream.error"
        assert "anthropic boom" in err[0].payload["error"]
        assert err[0].payload["message_id"] == "m_err"

    def test_openai_gateway_unaffected(self):
        """gateway=openai 仍走 OpenAI 客户端路径（回归保护）"""
        state = _make_state(gateway="openai")
        app_mod._get_llm_client = lambda cfg: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(
                create=lambda **kw: None  # 不会被调用：mock 前先断言走 openai 分支
            ))
        )
        # 直接验证 _stream_llm_response 分发
        async def _probe():
            called = {"n": 0}
            orig = app_mod._stream_openai_response

            async def fake_openai(*a, **kw):
                called["n"] += 1
                return ("", "", [], False, "")

            app_mod._stream_openai_response = fake_openai
            try:
                await app_mod._stream_llm_response(
                    llm_config={"gateway": "openai"},
                    llm_messages=[],
                    tool_schemas=[],
                    system_prompt="",
                    msg_id="m",
                    session_id="s",
                    output_queue=MockQueue(),
                    stream_chunk_timeout=5,
                )
            finally:
                app_mod._stream_openai_response = orig
            return called["n"]

        assert asyncio.run(_probe()) == 1
