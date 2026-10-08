# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""Optional MCP skill tests through FastClaw's loader and real HTTP transport."""

import asyncio
import importlib
import json
from pathlib import Path

import httpx
import pytest

pytest.importorskip("mcp", reason="Install parallel_search/requirements.txt to test MCP")

engine = importlib.import_module("core.app")
from core.bootstrap import copy_seed_files

ENDPOINT = "https://search.parallel.ai/mcp"
USER_AGENT = "FastClaw/parallel-search (+https://github.com/kandada/fastclaw)"


@pytest.fixture
def skill_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTCLAW_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("PARALLEL_API_KEY", "must-not-be-used")
    settings = tmp_path / "data/settings.json"
    settings.parent.mkdir()
    settings.write_text('{"default_agent_id": "my_saved_agent"}', encoding="utf-8")
    copy_seed_files(tmp_path)
    assert json.loads(settings.read_text())["default_agent_id"] == "my_saved_agent"
    original_skills = engine.SKILLS.copy()
    engine.SKILLS.clear()
    engine.SKILLS.update(engine.load_skills(str(tmp_path / "skills")))
    assert "parallel_search" in engine.SKILLS
    yield tmp_path
    engine.SKILLS.clear()
    engine.SKILLS.update(original_skills)


@pytest.fixture
def mcp_server(monkeypatch):
    calls = []
    control = {"error": False, "wait": False, "closed": False}

    async def handle(request):
        assert str(request.url) == ENDPOINT
        assert request.headers["User-Agent"] == USER_AGENT
        assert "authorization" not in request.headers
        if request.method != "POST":
            return httpx.Response(405)
        payload = json.loads(request.content)
        calls.append(payload)
        if "id" not in payload:
            return httpx.Response(202)
        if payload["method"] == "initialize":
            result = {
                "protocolVersion": "2025-11-25", "capabilities": {"tools": {}},
                "serverInfo": {"name": "fixture", "version": "1"},
            }
        elif payload["method"] == "tools/list":
            result = {"tools": [{"name": name, "inputSchema": {"type": "object"}}
                                for name in ("web_search", "web_fetch")]}
        else:
            assert payload["method"] == "tools/call"
            if control["wait"]:
                try:
                    await asyncio.Event().wait()
                finally:
                    control["closed"] = True
            result = {
                "content": [{"type": "text", "text": "https://docs.python.org/3/library/asyncio.html"},
                            {"type": "text", "text": "asyncio provides concurrent code using async/await"}],
                "isError": control["error"],
            }
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result})

    original = httpx.AsyncClient.__init__

    def init(client, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handle)
        original(client, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", init)
    return calls, control


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,arguments", [
    ("web_search", {"objective": "Find asyncio docs", "search_queries": ["Python asyncio documentation"]}),
    ("web_fetch", {"urls": ["https://docs.python.org/3/library/asyncio.html"], "objective": "Explain tasks"}),
])
async def test_dispatch(skill_workspace, mcp_server, tool, arguments):
    calls, _ = mcp_server
    out = await engine.run_skills("parallel_search", {"tool": tool, "arguments": arguments})
    assert "https://docs.python.org/3/library/asyncio.html\nasyncio provides" in out
    assert not out.startswith("Error")
    assert next(c for c in calls if c["method"] == "tools/call")["params"] == {
        "name": tool, "arguments": arguments,
    }
    for filename in ("main.py", "SKILL.md", "requirements.txt"):
        root = Path(__file__).resolve().parents[1]
        assert (root / "workspace/skills/bundled/parallel_search" / filename).read_bytes() == (
            skill_workspace / "skills/bundled/parallel_search" / filename
        ).read_bytes()


@pytest.mark.asyncio
async def test_tool_error(skill_workspace, mcp_server):
    _, control = mcp_server
    control["error"] = True
    out = await engine.run_skills("parallel_search", {"arguments": {"objective": "x", "search_queries": ["x"]}})
    assert out.startswith("Error: https://docs.python.org")


@pytest.mark.asyncio
async def test_invalid_params_do_not_connect(skill_workspace, mcp_server):
    calls, _ = mcp_server
    assert (await engine.run_skills("parallel_search", {"tool": "other", "arguments": {}})).startswith("Error:")
    assert (await engine.run_skills("parallel_search", {"arguments": "bad"})).startswith("Error:")
    assert not calls


@pytest.mark.asyncio
async def test_timeout_and_cancellation_close_request(skill_workspace, mcp_server):
    _, control = mcp_server
    control["wait"] = True
    params = {"arguments": {"objective": "x", "search_queries": ["x"]}}
    out = await engine.run_skills("parallel_search", params, timeout=0.1)
    assert "timed out" in out
    assert control["closed"]
    control["closed"] = False
    task = asyncio.create_task(engine.run_skills("parallel_search", params))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert control["closed"]


@pytest.mark.asyncio
async def test_agent_tool_round_trip(skill_workspace, mcp_server, monkeypatch):
    """A deterministic model fixture exercises the real agent/tools/agent cycle."""
    from fastmind import Event

    seen = []

    async def model_fixture(**kwargs):
        seen.append(kwargs["llm_messages"].copy())
        if len(seen) == 1:
            tool_call = {"id": "search-call", "function": {
                "name": "run_skills", "arguments": json.dumps({
                    "skill_name": "parallel_search", "params": {"arguments": {
                        "objective": "Find asyncio docs", "search_queries": ["Python asyncio documentation"],
                    }},
                }),
            }}
            return "", "", [tool_call], True, ""
        assert any(m.get("role") == "tool" and "docs.python.org" in m.get("content", "")
                   for m in kwargs["llm_messages"])
        return "asyncio documentation found", "", [], False, ""

    monkeypatch.setattr(engine, "_stream_llm_response", model_fixture)
    event = Event("user.message", {"text": "Find asyncio docs", "message_id": "search-test"}, "parallel-test")
    state = {"_session_id": "parallel-test", "_output_queue": asyncio.Queue(),
             "_agent_config": {}, "_personality": "", "messages": []}
    state = await engine.fastclaw_agent(state, event)
    assert engine.route(state, event) == "tools"
    state, events = await engine.tool_node.execute(state, event)
    assert events[0].type == "stream.tool_result"
    state = await engine.fastclaw_agent(state, event)
    assert state["messages"][-1]["content"] == "asyncio documentation found"
    assert len(seen) == 2
