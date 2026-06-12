"""上下文卸载与滑动窗口测试"""

from pathlib import Path

from core.app import (
    save_messages_to_jsonl,
    load_messages_from_jsonl,
    unload_early_messages,
    count_messages_tokens,
    CONTEXT_UNLOAD_THRESHOLD,
)
from core import config as config_module


def _patch_workspace(monkeypatch, tmp_path):
    ws = tmp_path / "fastclaw_ws"
    monkeypatch.setenv("FASTCLAW_WORKSPACE", str(ws))
    config_module.get_workspace_path.cache_clear()
    sessions_dir = ws / "data" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return ws


class TestUnloadEarlyMessages:
    """unload_early_messages 函数测试"""

    def test_unload_when_under_threshold(self):
        messages = [{"role": "user", "content": "hi"}]
        kept, unloaded = unload_early_messages(messages, 100000)
        assert len(kept) == 1
        assert len(unloaded) == 0

    def test_unload_when_over_threshold(self):
        messages = [{"role": "user", "content": "x" * 40000} for _ in range(10)]
        kept, unloaded = unload_early_messages(messages, 100)
        assert len(unloaded) > 0
        assert len(kept) < len(messages)

    def test_unload_keeps_tail(self):
        messages = [{"role": "user", "content": f"msg_{i}"} for i in range(20)]
        kept, unloaded = unload_early_messages(messages, 1)
        assert unloaded[0]["content"] == "msg_0"
        assert kept[0]["content"] != "msg_0"

    def test_unload_boundary_tool_calls(self):
        messages = [
            {"role": "user", "content": "tool1"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "function": {"name": "f", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "result1"},
            {"role": "user", "content": "tool2"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c2", "function": {"name": "f", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c2", "content": "result2"},
            {"role": "user", "content": "done"},
            {"role": "assistant", "content": "ok"},
        ]
        kept, unloaded = unload_early_messages(messages, 1)
        assert len(kept) > 0
        assert len(unloaded) > 0
        for m in kept:
            if m.get("role") == "tool":
                tool_id = m.get("tool_call_id")
                preceding = [km for km in kept[:kept.index(m)]
                             if km.get("role") == "assistant" and km.get("tool_calls")
                             and any(tc.get("id") == tool_id for tc in km.get("tool_calls", []))]
                assert len(preceding) > 0 or (
                    kept.index(m) > 0
                    and kept[kept.index(m) - 1].get("role") == "assistant"
                    and kept[kept.index(m) - 1].get("tool_calls")
                )


class TestLoadMessagesComplete:
    """验证 load_messages_from_jsonl 不会截断消息"""

    def test_load_returns_all_messages(self, tmp_path, monkeypatch):
        _patch_workspace(monkeypatch, tmp_path)
        session_id = "test_unload_complete"
        many_messages = [{"role": "user", "content": f"long message content line {i} " * 20} for i in range(50)]
        save_messages_to_jsonl(session_id, many_messages)
        loaded = load_messages_from_jsonl(session_id)
        assert len(loaded) == len(many_messages), "必须返回全部消息，不做截断"
        assert loaded[0]["content"] == many_messages[0]["content"]

    def test_load_with_over_threshold_messages(self, tmp_path, monkeypatch):
        _patch_workspace(monkeypatch, tmp_path)
        session_id = "test_unload_threshold"
        messages = [{"role": "user", "content": "x" * 5000} for _ in range(100)]
        total_tokens = count_messages_tokens(messages)
        assert total_tokens > CONTEXT_UNLOAD_THRESHOLD, "确保消息量超过阈值"
        save_messages_to_jsonl(session_id, messages)
        loaded = load_messages_from_jsonl(session_id)
        assert len(loaded) == len(messages), "即使超阈值也必须返回全部"


class TestSlidingWindow:
    """验证 state["messages"] 与 llm 输入的分离"""

    def test_sliding_window_does_not_mutate_state(self):
        state_messages = [{"role": "user", "content": "x" * 30000} for _ in range(10)]
        threshold = 100
        llm_messages = state_messages
        if count_messages_tokens(state_messages) >= threshold:
            llm_messages, _ = unload_early_messages(state_messages, threshold)
        assert len(state_messages) == 10, "state 必须保持完整"
        assert len(llm_messages) < len(state_messages), "llm 输入被截断"

    def test_sliding_window_returns_full_when_under_threshold(self):
        state_messages = [{"role": "user", "content": "hi"}]
        threshold = 100000
        llm_messages = state_messages
        if count_messages_tokens(state_messages) >= threshold:
            llm_messages, _ = unload_early_messages(state_messages, threshold)
        assert llm_messages is state_messages
        assert len(llm_messages) == 1
