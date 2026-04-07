"""测试 LLM streaming 的 chunk 到达时间间隔"""

import asyncio
import time
import os
import pytest
from openai import AsyncOpenAI


def _has_llm_config():
    """检查是否有可用的 LLM 配置"""
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    return bool(api_key)


@pytest.mark.skipif(
    not _has_llm_config(),
    reason="Requires LLM_API_KEY or OPENAI_API_KEY environment variable",
)
@pytest.mark.asyncio
async def test_llm_streaming_timing():
    """测试 LLM streaming 时 chunk 到达的时间间隔"""
    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_API_URL", "https://api.deepseek.com/v1")

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    print("\nTesting DeepSeek streaming timing...")
    print("=" * 60)

    start_time = None
    last_time = None
    chunk_count = 0
    intervals = []

    stream = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "写一首关于春天的诗，五言绝句就好"}],
        stream=True,
    )

    async for chunk in stream:
        current_time = time.time()

        if start_time is None:
            start_time = current_time
            last_time = current_time

        delta = chunk.choices[0].delta.content or ""
        if delta:
            interval = current_time - last_time
            intervals.append(interval)
            chunk_count += 1
            elapsed = current_time - start_time

            print(
                f"chunk {chunk_count:3d}: +{interval * 1000:6.1f}ms | elapsed {elapsed * 1000:6.1f}ms | content: {delta!r}"
            )

        last_time = current_time

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
    asyncio.run(test_llm_streaming_timing())
