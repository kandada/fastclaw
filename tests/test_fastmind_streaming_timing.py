"""测试 FastMind stream_events 的 chunk 到达时间间隔"""

import pytest
import asyncio
import time
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastmind import Event


@pytest.mark.asyncio
async def test_fastmind_streaming_timing(shared_api):
    """测试 FastMind stream_events 时 chunk 到达的时间间隔"""
    print("Testing FastMind streaming timing via stream_events...")
    print("=" * 60)

    session_id = "test_stream_session"

    await shared_api.push_event(
        session_id, Event("user.message", {"text": "hi"}, session_id)
    )

    start_time = None
    last_time = None
    chunk_count = 0
    intervals = []

    async for event in shared_api.stream_events(session_id):
        current_time = time.time()

        if start_time is None:
            start_time = current_time
            last_time = current_time

        if event.type == "stream.chunk":
            interval = current_time - last_time
            intervals.append(interval)
            chunk_count += 1
            elapsed = current_time - start_time

            delta = event.payload.get("delta", "")
            print(
                f"chunk {chunk_count:3d}: +{interval * 1000:6.1f}ms | elapsed {elapsed * 1000:6.1f}ms | content: {delta!r}"
            )

        last_time = current_time

        if event.type in ("stream.end", "error"):
            break

    print("=" * 60)
    if intervals:
        intervals_sorted = sorted(intervals)
        avg_interval = sum(intervals) / len(intervals)
        median_interval = intervals_sorted[len(intervals_sorted) // 2]
        max_interval = max(intervals)
        min_interval = min(intervals)

        print(f"Total chunks: {chunk_count}")
        print(f"Total time: {(last_time - start_time) * 1000:.1f}ms")
        print(f"Avg interval: {avg_interval * 1000:.1f}ms")
        print(f"Median interval: {median_interval * 1000:.1f}ms")
        print(f"Min interval: {min_interval * 1000:.1f}ms")
        print(f"Max interval: {max_interval * 1000:.1f}ms")

        print("\nSlowest chunks (top 5):")
        for i, interval in enumerate(sorted(intervals, reverse=True)[:5]):
            print(f"  {i + 1}. {interval * 1000:.1f}ms")


if __name__ == "__main__":
    pytest.skip("Run with: pytest tests/test_fastmind_streaming_timing.py -v -s")
