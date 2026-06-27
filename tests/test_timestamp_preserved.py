# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""验证时间戳在多次保存后不被覆盖"""

import json
from pathlib import Path

from core.app import save_messages_to_jsonl, load_messages_from_jsonl
from core import config as config_module


def _patch_workspace(monkeypatch, tmp_path):
    ws = tmp_path / "fastclaw_ws"
    monkeypatch.setenv("FASTCLAW_WORKSPACE", str(ws))
    config_module.get_workspace_path.cache_clear()
    sessions_dir = ws / "data" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return ws


def test_timestamp_mutates_original_object(tmp_path, monkeypatch):
    _patch_workspace(monkeypatch, tmp_path)
    session_id = "test_ts_mutate"
    orig_user = {"role": "user", "content": "hello"}
    messages = [orig_user]

    save_messages_to_jsonl(session_id, messages)

    ts1 = orig_user.get("timestamp")
    assert ts1 is not None, "save 后原对象应被添加上 timestamp"

    for i in range(5):
        messages.append({"role": "assistant", "content": f"response {i}"})
        save_messages_to_jsonl(session_id, messages)

    assert orig_user["timestamp"] == ts1, (
        f"多次保存后 user 的 timestamp 不应改变: 预期 {ts1}, 实际 {orig_user['timestamp']}"
    )


def test_save_preserves_loaded_timestamps(tmp_path, monkeypatch):
    ws = _patch_workspace(monkeypatch, tmp_path)
    session_id = "test_ts_preserve"
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
    ]

    save_messages_to_jsonl(session_id, messages)

    loaded = load_messages_from_jsonl(session_id)
    orig_ts = [m.get("timestamp") for m in loaded]
    assert all(orig_ts), "所有加载的消息应有 timestamp"

    loaded.append({"role": "user", "content": "second"})
    save_messages_to_jsonl(session_id, loaded)

    disk_path = ws / "data" / "sessions" / session_id / "messages.jsonl"
    with open(disk_path) as f:
        lines = f.read().strip().split("\n")

    disk_msgs = [json.loads(line) for line in lines]
    assert len(disk_msgs) == 3

    for i, (disk_msg, expected_ts) in enumerate(zip(disk_msgs[:2], orig_ts)):
        assert disk_msg["timestamp"] == expected_ts, (
            f"第 {i} 条消息的 timestamp 被覆盖: 预期 {expected_ts}, 实际 {disk_msg['timestamp']}"
        )

    assert disk_msgs[2].get("timestamp") is not None, "新消息应有 timestamp"
