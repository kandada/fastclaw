# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""WebUI 消息对话 UI 重构专项测试

覆盖 2026-08 消息对话 UI 大重构引入的改动：
- app.py: ToolNodeWithEvents 发出 stream.tool_result 事件
- router.py: stream.tool_result -> message.tool_result SSE 映射 + 会话状态恢复字段
- webui/index.html: 统一消息块模型（thinking/tool_call/tool_result/text）、
  折叠渲染模板、历史重建、断线恢复、流动灯条
"""

import asyncio
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

from fastmind import Event, Tool

from core.app import ToolNodeWithEvents
from gateway.router import (
    _transform_event_to_sse,
    _update_session_stream_state,
    chat_stream_state,
)

WEBUI_INDEX = Path(__file__).parent.parent / "webui" / "index.html"


# ---------------------------------------------------------------------------
# 1. SSE 事件转换：stream.tool_result -> message.tool_result
# ---------------------------------------------------------------------------
class TestSSEToolResultTransform:
    """tool_result 事件转换测试（本次重构核心新增通道）"""

    def test_tool_result_mapping(self):
        ev = Event(
            type="stream.tool_result",
            payload={
                "tool_call_id": "call_abc",
                "tool_name": "run_shell",
                "result": "guangzhou: ☀️ +30°C\nline2",
            },
            session_id="s1",
        )
        sse = _transform_event_to_sse(ev, "msg-1")
        assert sse is not None
        assert sse["event"] == "message.tool_result"
        assert sse["id"] == "msg-1"
        assert sse["data"]["tool_call_id"] == "call_abc"
        assert sse["data"]["tool_name"] == "run_shell"
        assert sse["data"]["result"].startswith("guangzhou")

    def test_tool_result_without_target_id(self):
        """无 target_message_id 时保持 message_id 兜底"""
        ev = Event(
            type="stream.tool_result",
            payload={"tool_call_id": "c", "tool_name": "t", "result": "r"},
            session_id="s1",
        )
        sse = _transform_event_to_sse(ev)
        assert sse["event"] == "message.tool_result"
        assert sse["id"] == "unknown"

    def test_tool_result_empty_result(self):
        ev = Event(
            type="stream.tool_result",
            payload={"tool_call_id": "c", "tool_name": "t", "result": ""},
            session_id="s1",
        )
        sse = _transform_event_to_sse(ev, "m")
        assert sse["data"]["result"] == ""

    def test_tool_start_mapping_preserved(self):
        """tool_start(fragment) 原有行为不被破坏"""
        ev = Event(
            type="stream.fragment",
            payload={
                "has_tool_calls": True,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "run_shell", "arguments": '{"command": "ls"}'},
                    }
                ],
            },
            session_id="s1",
        )
        sse = _transform_event_to_sse(ev, "m")
        assert sse["event"] == "message.tool_start"
        assert "Executing tool" in sse["data"]["tool_info"]
        assert len(sse["data"]["tool_calls"]) == 1

    def test_chunk_thinking_end_preserved(self):
        """原有 chunk/thinking/end 映射不受影响"""
        for etype, payload, expected in [
            ("stream.chunk", {"delta": "hi"}, "message.chunk"),
            ("stream.thinking", {"delta": "think"}, "message.thinking"),
            ("stream.end", {}, "message.end"),
        ]:
            sse = _transform_event_to_sse(
                Event(type=etype, payload=payload, session_id="s1"), "m"
            )
            assert sse["event"] == expected

    def test_unknown_event_skipped(self):
        """未知/内部事件类型应被忽略（不影响其他渠道）"""
        for etype in ("user.message", "interrupt", "cron.message"):
            sse = _transform_event_to_sse(
                Event(type=etype, payload={}, session_id="s1"), "m"
            )
            if etype == "cron.message":
                assert sse is not None
            else:
                assert sse is None

    def test_transform_does_not_mutate_original_payload(self):
        """_transform_event_to_sse 不应修改原始 event.payload（多消费者共享同一事件）"""
        payload = {"delta": "hi"}
        ev = Event(type="stream.chunk", payload=payload, session_id="s1")
        _transform_event_to_sse(ev, "m")
        # 原始 payload 不应被塞入 message_id（data 应是浅拷贝）
        assert payload == {"delta": "hi"}

    def test_transform_data_carries_message_id(self):
        """chunk 事件的 data 应携带 message_id（浅拷贝后追加）"""
        ev = Event(type="stream.chunk", payload={"delta": "hi"}, session_id="s1")
        sse = _transform_event_to_sse(ev, "m")
        assert sse["data"]["message_id"] == "m"
        assert sse["data"]["delta"] == "hi"


# ---------------------------------------------------------------------------
# 2. 会话流式状态恢复字段（断线恢复需重建 blocks）
# ---------------------------------------------------------------------------
class TestChatStreamStateRecovery:
    """chat_stream_state 恢复字段测试"""

    def test_state_default_has_tool_fields(self):
        state = asyncio.run(chat_stream_state("nonexistent_session_xyz"))
        assert state["message_id"] is None
        assert state["content"] == ""
        assert state["thinking"] == ""
        assert state["tool_calls"] == []
        assert state["tool_results"] == []


# ---------------------------------------------------------------------------
# 2.5 _update_session_stream_state：断线恢复状态累积
# ---------------------------------------------------------------------------
class TestUpdateSessionStreamState:
    """SSE 会话恢复状态更新逻辑测试（重构提取的纯函数）"""

    def _sse(self, evt, **data):
        return {"id": "m1", "event": evt, "data": data}

    def test_chunk_thinking_accumulate(self):
        state = {"message_id": "m1", "content": "", "thinking": "",
                 "tool_calls": [], "tool_results": [], "role": "assistant"}
        state = _update_session_stream_state(state, self._sse("message.chunk", delta="hi "))
        state = _update_session_stream_state(state, self._sse("message.chunk", delta="there"))
        state = _update_session_stream_state(state, self._sse("message.thinking", delta="think"))
        assert state["content"] == "hi there"
        assert state["thinking"] == "think"

    def test_tool_events_accumulate(self):
        state = {"message_id": "m1", "content": "", "thinking": "",
                 "tool_calls": [], "tool_results": [], "role": "assistant"}
        state = _update_session_stream_state(
            state, self._sse("message.tool_start",
                             tool_calls=[{"id": "c1", "function": {"name": "run_shell"}}])
        )
        state = _update_session_stream_state(
            state, self._sse("message.tool_result",
                             tool_call_id="c1", tool_name="run_shell", result="out")
        )
        assert len(state["tool_calls"]) == 1
        assert state["tool_calls"][0]["id"] == "c1"
        assert len(state["tool_results"]) == 1
        assert state["tool_results"][0]["result"] == "out"

    def test_pure_tool_stream_initializes_state(self):
        """无 message.start 的纯工具流：tool 事件先到时自动初始化恢复状态"""
        state = _update_session_stream_state(
            None, self._sse("message.tool_start",
                            tool_calls=[{"id": "c1", "function": {"name": "run_shell"}}]),
            current_msg_id="m_pure",
        )
        assert state is not None
        assert state["message_id"] == "m_pure"
        assert state["tool_calls"] == [{"id": "c1", "function": {"name": "run_shell"}}]
        # tool_result 继续累积
        state = _update_session_stream_state(
            state, self._sse("message.tool_result",
                             tool_call_id="c1", tool_name="run_shell", result="out")
        )
        assert state["tool_results"] == [
            {"tool_call_id": "c1", "tool_name": "run_shell", "result": "out"}
        ]
        # 后续 chunk 正常累积
        state = _update_session_stream_state(state, self._sse("message.chunk", delta="answer"))
        assert state["content"] == "answer"

    def test_pure_tool_result_first(self):
        """tool_result 最先到达（极端）时也可初始化"""
        state = _update_session_stream_state(
            None, self._sse("message.tool_result",
                            tool_call_id="c1", tool_name="t", result="r"),
            current_msg_id=None,
        )
        assert state is not None
        assert state["message_id"] == "m1"  # 回退到 sse id
        assert state["tool_results"][0]["result"] == "r"

    def test_non_tool_event_without_state_returns_none(self):
        """非工具事件且无状态时不初始化（避免脏数据）"""
        assert _update_session_stream_state(None, self._sse("message.chunk", delta="x")) is None
        assert _update_session_stream_state(None, self._sse("message.thinking", delta="x")) is None

    def test_state_mutation_returns_same_dict(self):
        """状态存在时原地更新并返回同一引用（与生成器赋值兼容）"""
        state = {"message_id": "m1", "content": "", "thinking": "",
                 "tool_calls": [], "tool_results": [], "role": "assistant"}
        out = _update_session_stream_state(state, self._sse("message.chunk", delta="d"))
        assert out is state


# ---------------------------------------------------------------------------
# 3. ToolNodeWithEvents：工具执行后发出 stream.tool_result 事件
# ---------------------------------------------------------------------------
class TestToolNodeWithEvents:
    """app.py 中 ToolNodeWithEvents 的行为测试"""

    def _make_node(self, result="shell output: ok"):
        tool = Tool(name="run_shell", description="", func=lambda command="": result)
        return ToolNodeWithEvents({"run_shell": tool})

    def _make_state(self, session_id="test_sess", tool_id="call_1"):
        return {
            "_session_id": session_id,
            "tool_calls": [
                {
                    "id": tool_id,
                    "type": "function",
                    "function": {"name": "run_shell", "arguments": '{"command": "ls"}'},
                }
            ],
        }

    def test_emits_tool_result_event(self):
        node = self._make_node()
        state = self._make_state()
        event = Event(type="user.message", payload={}, session_id="test_sess")

        new_state, output_events = asyncio.run(node.execute(state, event))

        # 结果仍写入 state.tool_results（原有行为保留）
        assert new_state["tool_results"] == [
            {"tool_call_id": "call_1", "tool_name": "run_shell", "result": "shell output: ok"}
        ]
        # 新增：发出 stream.tool_result 事件
        assert [e.type for e in output_events] == ["stream.tool_result"]
        ev = output_events[0]
        assert ev.payload["tool_name"] == "run_shell"
        assert ev.payload["tool_call_id"] == "call_1"
        assert ev.payload["result"] == "shell output: ok"
        assert ev.session_id == "test_sess"

    def test_emits_tool_result_event_with_message_id(self):
        """state._message_id 存在时，tool_result 事件应携带 message_id"""
        node = self._make_node()
        state = self._make_state()
        state["_message_id"] = "msg_123"
        event = Event(type="user.message", payload={"message_id": "msg_123"}, session_id="test_sess")

        _, output_events = asyncio.run(node.execute(state, event))
        ev = output_events[0]
        assert ev.payload["message_id"] == "msg_123"

    def test_no_tool_calls_no_events(self):
        node = self._make_node()
        state = {"_session_id": "test_sess"}  # 无 tool_calls
        event = Event(type="user.message", payload={}, session_id="test_sess")

        new_state, output_events = asyncio.run(node.execute(state, event))
        assert new_state.get("tool_results") is None
        assert output_events == []

    def test_multiple_tool_calls_multiple_events(self):
        tool1 = Tool(name="run_shell", description="", func=lambda command="": "out1")
        tool2 = Tool(name="run_skills", description="", func=lambda name="": "out2")
        node = ToolNodeWithEvents({"run_shell": tool1, "run_skills": tool2})
        state = {
            "_session_id": "s1",
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "run_shell", "arguments": "{}"}},
                {"id": "c2", "type": "function", "function": {"name": "run_skills", "arguments": "{}"}},
            ],
        }
        event = Event(type="user.message", payload={}, session_id="s1")
        new_state, output_events = asyncio.run(node.execute(state, event))
        assert [e.type for e in output_events] == ["stream.tool_result", "stream.tool_result"]
        names = {e.payload["tool_name"] for e in output_events}
        assert names == {"run_shell", "run_skills"}
        assert len(new_state["tool_results"]) == 2

    def test_unknown_tool_result(self):
        """工具不存在时也发出事件（携带错误信息，与 jsonl 落盘一致）"""
        node = self._make_node()
        state = self._make_state(tool_id="c9")
        state["tool_calls"][0]["function"]["name"] = "no_such_tool"
        event = Event(type="user.message", payload={}, session_id="test_sess")

        new_state, output_events = asyncio.run(node.execute(state, event))
        assert output_events[0].type == "stream.tool_result"
        assert "not found" in output_events[0].payload["result"]
        assert output_events[0].payload["tool_name"] == "no_such_tool"


# ---------------------------------------------------------------------------
# 4. Agents API 回归（list_agents 装饰器修复）
# ---------------------------------------------------------------------------
class TestAgentsAPIRegression:
    """GET /api/agents 路由回归（修复 @router.get 装饰器丢失）"""

    def test_agents_get_200(self):
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()
        with TestClient(server.app) as client:
            response = client.get("/api/agents")
            assert response.status_code == 200
            data = response.json()
            assert "agents" in data
            assert isinstance(data["agents"], list)

    def test_agents_get_returns_configured(self):
        """能列出 workspace 中已配置的 agent（非空列表）"""
        from fastapi.testclient import TestClient
        from gateway.server import GatewayServer

        server = GatewayServer()
        with TestClient(server.app) as client:
            response = client.get("/api/agents")
            assert response.status_code == 200
            names = [a.get("name") for a in response.json().get("agents", [])]
            # workspace 有 main_agent / deepseek-chat / MiniMax-M2.7 配置
            assert "main_agent" in names


# ---------------------------------------------------------------------------
# 5. WebUI 前端完整性（index.html）
# ---------------------------------------------------------------------------
class TestWebUIFrontendIntegrity:
    """index.html 重构后结构完整性检查"""

    def _src(self):
        assert WEBUI_INDEX.exists(), f"{WEBUI_INDEX} 不存在"
        return WEBUI_INDEX.read_text(encoding="utf-8")

    def _inline_scripts(self, src):
        return re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", src, re.S)

    def test_html_tags_balanced(self):
        """HTML 标签配对完整（无未闭合标签）"""
        VOID = {
            "meta", "link", "br", "img", "input", "hr", "source",
            "area", "base", "col", "embed", "track", "wbr",
        }

        class Checker(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.stack = []
                self.errors = []

            def handle_starttag(self, tag, attrs):
                if tag not in VOID:
                    self.stack.append((tag, self.getpos()))

            def handle_endtag(self, tag):
                if tag in VOID:
                    return
                if self.stack and self.stack[-1][0] == tag:
                    self.stack.pop()
                elif tag in [t for t, _ in self.stack]:
                    while self.stack and self.stack[-1][0] != tag:
                        self.errors.append(
                            f"unclosed <{self.stack[-1][0]}> at {self.stack[-1][1]}"
                        )
                        self.stack.pop()
                    self.stack.pop()
                else:
                    self.errors.append(f"mismatch </{tag}> at {self.getpos()}")

        c = Checker()
        c.feed(self._src())
        for t, pos in c.stack:
            c.errors.append(f"unclosed <{t}> at {pos}")
        assert not c.errors, c.errors[:10]

    def test_no_stale_legacy_references(self):
        """旧渲染函数/字段无残留（重构彻底性）"""
        src = self._src()
        for stale in ("getMsgContent", "renderPlainText", "msg.segments",
                      "thinking-content", "tool_infos"):
            assert stale not in src, f"残留旧代码引用: {stale}"

    def test_block_model_functions_present(self):
        """统一块模型核心函数齐全"""
        src = self._src()
        required = [
            "function newAssistantMessage", "function ensureBlock",
            "function prettyJson", "function ensureToolCallBlock",
            "function addToolResultBlock", "function queueTextDelta",
            "function queueThinkingDelta", "function flushPendingDeltas",
            "function addErrorBlock",
            "function settleMessage", "function onBlockToggle",
            "function copyBlock", "function buildHistoryMessages",
        ]
        for fn in required:
            assert fn in src, f"缺少函数: {fn}"

    def test_reactive_imported(self):
        """Vue reactive 已解构（流式响应式渲染的前提）"""
        src = self._src()
        assert "reactive" in re.search(
            r"const \{.*\} = Vue;", src, re.S
        ).group(0), "Vue 解构缺少 reactive"

    def test_block_templates_present(self):
        """折叠块模板齐全（thinking/tool_call/tool_result/text/error）"""
        src = self._src()
        for cls in (
            "block-card thinking-card", "block-card tool-call-card",
            "block-card tool-result-card", "text-block", "error-block",
        ):
            assert cls in src, f"缺少模板: {cls}"

    def test_sse_tool_result_handler_present(self):
        """前端注册了 message.tool_result SSE 处理器"""
        src = self._src()
        assert "addEventListener('message.tool_result'" in src

    def test_history_merge_uses_build_history(self):
        """selectSession 使用 buildHistoryMessages 重建（turn 合并）"""
        src = self._src()
        assert "messages.value = buildHistoryMessages(loadedMessages)" in src

    def test_stream_bar_present(self):
        """运行中流动灯条模板存在"""
        src = self._src()
        assert "stream-bar-wrap" in src
        assert "isStreaming || isSending" in src
        assert "stream-slide" in src

    def test_js_syntax_valid(self):
        """内联 JS 语法检查（node 可用时）"""
        if not shutil.which("node"):
            pytest.skip("node 不可用，跳过 JS 语法检查")
        scripts = self._inline_scripts(self._src())
        assert len(scripts) >= 1
        tmp = Path("/tmp") / "webui_index_inline.js"
        tmp.write_text(scripts[-1], encoding="utf-8")
        r = subprocess.run(
            ["node", "--check", str(tmp)],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr[:500]

    def test_vue_app_script_complete(self):
        """Vue setup 脚本块完整（含 createApp/mount）"""
        src = self._src()
        assert "createApp" in src
        assert "app.mount('#app')" in src


# ---------------------------------------------------------------------------
# 6. WebUI 前端行为逻辑（纯 JS 函数，通过 node 提取验证）
# ---------------------------------------------------------------------------
class TestWebUIFrontendLogic:
    """通过 node 执行内联脚本中的纯函数，验证历史重建/块构建逻辑"""

    @pytest.fixture(scope="class")
    def node_env(self):
        if not shutil.which("node"):
            pytest.skip("node 不可用，跳过行为逻辑测试")
        src = Path(__file__).parent.parent.joinpath(
            "webui", "index.html"
        ).read_text(encoding="utf-8")
        scripts = re.findall(
            r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", src, re.S
        )
        # 提取 Vue setup 内的函数定义（在 setup() 函数体中），剥离 Vue API 依赖
        body = scripts[-1]
        # 取出 setup 函数体内从 newAssistantMessage 到 buildHistoryMessages 之间的纯函数定义
        start = body.index("function newAssistantMessage")
        end = body.index("async function loadSessions")
        funcs = body[start:end]
        # 移除对 Vue reactive 的依赖：newAssistantMessage 里用了 reactive()
        funcs = funcs.replace(
            "return reactive(raw);",
            "return raw;",  # node 环境无 Vue，退化为普通对象（仅测数据逻辑）
        )
        probe = r"""
const history = [
  {role: "user", content: "今天天气怎么样", timestamp: 100},
  {role: "assistant", content: "",
   reasoning_content: "思考中", tool_calls: [
     {id: "c1", type: "function", function: {name: "run_shell", arguments: '{"command": "ls"}'}}],
   timestamp: 101},
  {role: "tool", tool_call_id: "c1", content: "[run_shell]: output line", timestamp: 102},
  {role: "assistant", content: "**总结**回答", reasoning_content: "思考2", timestamp: 103},
  {role: "user", content: "再问", timestamp: 104},
  {role: "assistant", content: "直接回答", timestamp: 105},
];
const turns = buildHistoryMessages(history);
const out = {
  turnCount: turns.length,
  roles: turns.map(t => t.role),
  blockTypes: turns.filter(t => t.role === 'assistant').map(t => t.blocks.map(b => b.type)),
  merged: turns[1].blocks.map(b => b.type),
  thinkingText: turns[1].blocks[0].text,
  toolCallName: turns[1].blocks[1].name,
  toolResultText: turns[1].blocks[2].text,
  finalText: turns[1].blocks[3].text,
  plainAnswer: turns[3].blocks.map(b => b.type),
};
console.log(JSON.stringify(out));
const history2 = [
  {role: "user", content: "q", timestamp: 1},
  {role: "assistant", content: "", reasoning_content: "r1", tool_calls: [
    {id: "a1", type: "function", function: {name: "run_shell", arguments: '{"cmd":"1"}'}}], timestamp: 2},
  {role: "tool", tool_call_id: "a1", content: "[run_shell]: out1", timestamp: 3},
  {role: "assistant", content: "", reasoning_content: "r2", tool_calls: [
    {id: "a2", type: "function", function: {name: "run_skills", arguments: '{"name":"x"}'}}], timestamp: 4},
  {role: "tool", tool_call_id: "a2", content: "[run_skills]: out2", timestamp: 5},
  {role: "assistant", content: "最终回答", reasoning_content: "r3", timestamp: 6},
];
const turns2 = buildHistoryMessages(history2);
out.toolchainBlocks = turns2[1].blocks.map(b => b.type);
out.toolchainNames = turns2[1].blocks.filter(b => b.type === 'tool_call' || b.type === 'tool_result').map(b => b.name);
out.toolchainTurnCount = turns2.length;
console.log(JSON.stringify(out));
"""
        # node 环境无 Vue，reactive 退化为 identity（仅测数据逻辑）
        runner = "const reactive = (x) => x;\n" + funcs + "\n" + probe
        import json
        r = subprocess.run(
            ["node", "-e", runner],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, f"node 执行失败: {r.stderr[:500]}"
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_history_turn_merge(self, node_env):
        """assistant(tool_calls)+tool+assistant(回答) 合并为同一气泡"""
        assert node_env["turnCount"] == 4  # user, merged, user, plain
        # thinking 属于同一轮 ReAct 的推理通道：合并为单块，不被切分
        assert node_env["blockTypes"] == [
            ["thinking", "tool_call", "tool_result", "text"],
            ["text"],
        ]
        assert node_env["merged"] == [
            "thinking", "tool_call", "tool_result", "text",
        ]
        assert node_env["thinkingText"] == "思考中\n\n思考2"
        assert node_env["toolCallName"] == "run_shell"
        assert node_env["toolResultText"] == "output line"
        assert node_env["finalText"] == "**总结**回答"

    def test_plain_answer_separate_turn(self, node_env):
        """无工具关联的独立回答应保持独立气泡"""
        assert node_env["plainAnswer"] == ["text"]

    def test_multi_tool_chain_merges_into_one_turn(self, node_env):
        """多轮工具链 tc→tool→tc→tool→answer 合并为同一气泡（与流式一致）"""
        assert node_env["toolchainTurnCount"] == 2  # user + merged turn
        # 多轮工具链的推理内容合并为单个 thinking 块（与流式视图一致）
        assert node_env["toolchainBlocks"] == [
            "thinking", "tool_call", "tool_result",
            "tool_call", "tool_result",
            "text",
        ]
        # tool_call 保留工具名；tool_result 统一显示为 "tool"（数据层已去掉 [name] 前缀）
        assert node_env["toolchainNames"] == [
            "run_shell", "tool", "run_skills", "tool",
        ]


def json_quote(s):
    """将 JS 代码转为 node -e 可用的单行字符串"""
    import json as _json
    return _json.dumps(s)
