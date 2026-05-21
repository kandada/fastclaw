"""验证时间戳在多次保存后不被覆盖"""

import json
import time
from pathlib import Path

from core.app import save_messages_to_jsonl, load_messages_from_jsonl


def test_timestamp_mutates_original_object():
    """验证 save 会原地修改 msg 对象，使后续 save 不再覆盖时间戳"""
    session_id = "test_ts_mutate"

    orig_user = {"role": "user", "content": "hello"}
    messages = [orig_user]

    save_messages_to_jsonl(session_id, messages)

    ts1 = orig_user.get("timestamp")
    assert ts1 is not None, "save 后原对象应被添加上 timestamp"

    # 模拟多次保存（如多轮对话中反复全量保存）
    for i in range(5):
        messages.append({"role": "assistant", "content": f"response {i}"})
        save_messages_to_jsonl(session_id, messages)

    # 验证原 user 消息的 timestamp 始终不变
    assert orig_user["timestamp"] == ts1, (
        f"多次保存后 user 的 timestamp 不应改变: 预期 {ts1}, 实际 {orig_user['timestamp']}"
    )


def test_save_preserves_loaded_timestamps():
    """验证从磁盘加载后再次保存，时间戳不被覆盖"""
    session_id = "test_ts_preserve"

    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
    ]

    save_messages_to_jsonl(session_id, messages)

    loaded = load_messages_from_jsonl(session_id)
    orig_ts = [m.get("timestamp") for m in loaded]
    assert all(orig_ts), "所有加载的消息应有 timestamp"

    # 追加新消息并再次保存（模拟下一轮对话）
    loaded.append({"role": "user", "content": "second"})
    save_messages_to_jsonl(session_id, loaded)

    # 从磁盘验证旧消息的时间戳未被覆盖
    disk_path = Path(f"workspace/data/sessions/{session_id}/messages.jsonl")
    with open(disk_path) as f:
        lines = f.read().strip().split("\n")

    disk_msgs = [json.loads(line) for line in lines]
    assert len(disk_msgs) == 3

    for i, (disk_msg, expected_ts) in enumerate(zip(disk_msgs[:2], orig_ts)):
        assert disk_msg["timestamp"] == expected_ts, (
            f"第 {i} 条消息的 timestamp 被覆盖: 预期 {expected_ts}, 实际 {disk_msg['timestamp']}"
        )

    assert disk_msgs[2].get("timestamp") is not None, "新消息应有 timestamp"
