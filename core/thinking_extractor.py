# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""OpenAI 兼容流中 thinking / reasoning 内容的统一提取器

背景：
- 各家"OpenAI 兼容"提供商对推理模型（reasoning model）的 thinking 字段没有统一标准
- DeepSeek / Kimi-K2-thinking: 独立字段 ``reasoning_content``
- 部分私有代理（含 MiniMax 系）: 独立字段 ``thinking``
- Qwen3 系（含部分国内代理）: 嵌入 ``delta.content`` 的 ``<think>...</think>`` 标签
- 历史代码只识别 ``reasoning_content``，导致其他格式下 thinking 不显示

模块对外暴露：
- ``OpenAIThinkingExtractor``: 流式提取器，喂 delta 吐 (think_chunk, content_chunk)
- ``strip_thinking_prefixes``: 清理正文开头残留的 "Thought:" 等前缀

设计原则：
- 字段策略优先级 > 标签策略：避免同响应里两种格式并存时重复计数
- 状态机式标签解析：处理跨 chunk 切分的标签（如 ``<th`` 与 ``ink>`` 分两个 chunk）
- 纯输入输出工具，不耦合 OpenAI SDK / asyncio / session
"""

import re
from typing import Tuple


class _TagParser:
    """``<think>...</think>`` 标签的有状态流式解析器。

    内部维护一个 ``MAX_TAG_LEN`` 长度的回看缓冲，保证跨 chunk 切分的标签
    也能被正确识别（例如 ``<th`` 在 chunk N、``ink>`` 在 chunk N+1）。
    """

    TAG_OPEN = "<think>"
    TAG_CLOSE = "</think>"
    TAG_PATTERN = re.compile(r"<think>|</think>")
    MAX_TAG_LEN = max(len(TAG_OPEN), len(TAG_CLOSE))  # 8

    def __init__(self):
        self._buffer = ""
        self._in_think = False

    def feed(self, content_chunk: str) -> Tuple[str, str]:
        """喂入一个 chunk，返回 (think_chunk, content_chunk) 用于立即输出。

        两者都可能是空串，调用方按现有累加逻辑拼接即可。
        """
        if not content_chunk:
            return ("", "")

        full = self._buffer + content_chunk
        out_think = ""
        out_content = ""
        last_safe_idx = 0

        for match in self.TAG_PATTERN.finditer(full):
            seg_start = match.start()
            seg_end = match.end()
            tag = match.group()

            segment = full[last_safe_idx:seg_start]
            if self._in_think:
                out_think += segment
            else:
                out_content += segment

            self._in_think = (tag == self.TAG_OPEN)
            last_safe_idx = seg_end

        remaining = full[last_safe_idx:]
        if self._in_think:
            # 思考中：残余可能是思考内容，也可能是 </think> 的起始片段
            # 没法提前判断，必须缓冲 MAX_TAG_LEN 以捕获跨 chunk 标签
            if len(remaining) > self.MAX_TAG_LEN:
                emit = remaining[: -self.MAX_TAG_LEN]
                self._buffer = remaining[-self.MAX_TAG_LEN:]
                out_think += emit
            else:
                self._buffer = remaining
        else:
            # 普通模式：若残余不以 '<' 起头，绝不可能是标签起始 → 立即输出
            if not remaining.startswith("<"):
                out_content += remaining
                self._buffer = ""
            elif len(remaining) > self.MAX_TAG_LEN:
                emit = remaining[: -self.MAX_TAG_LEN]
                self._buffer = remaining[-self.MAX_TAG_LEN:]
                out_content += emit
            else:
                self._buffer = remaining

        return (out_think, out_content)

    def finalize(self) -> Tuple[str, str]:
        """流结束时刷一次残余缓冲。"""
        if not self._buffer:
            return ("", "")
        out = self._buffer
        self._buffer = ""
        if self._in_think:
            return (out, "")
        return ("", out)


class OpenAIThinkingExtractor:
    """OpenAI 兼容流式响应中 thinking 内容的统一提取器。

    策略优先级（高 → 低）：
    1. 字段策略：``delta.reasoning_content``（DeepSeek / Kimi 风格）
    2. 字段策略：``delta.thinking``（部分私有协议，如 MiniMax 系）
    3. 标签策略：``delta.content`` 中的 ``<think>...</think>``（Qwen 风格）

    字段策略命中时，``delta.content`` 直接透传（不再走标签解析），避免
    "字段式 reasoning_content + 标签式 content" 并存时被双重计数。
    """

    STRATEGY_FIELDS = ("reasoning_content", "thinking")

    def __init__(self):
        self._tag_parser = _TagParser()

    def feed(self, delta) -> Tuple[str, str]:
        """处理一个流式 delta，返回 (think_chunk, content_chunk)。"""
        # ── Layer A：字段策略 ──
        for field in self.STRATEGY_FIELDS:
            val = getattr(delta, field, None)
            if val:
                content = getattr(delta, "content", None) or ""
                return (val, content)

        # ── Layer B：标签策略 ──
        content = getattr(delta, "content", None) or ""
        return self._tag_parser.feed(content)

    def finalize(self) -> Tuple[str, str]:
        """流结束时回收标签解析器的残余缓冲。"""
        return self._tag_parser.finalize()
