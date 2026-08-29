# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""Anthropic 网关 thinking 启用的状态机控制

背景：
- Anthropic 协议的 thinking 配置有两种 type：
  * ``adaptive``: 无需 budget_tokens，Claude 4.6+ 主流，未来兼容
  * ``enabled``: 必须有 budget_tokens (≥1024 且 < max_tokens)，Claude 4.5 及更早
- 不同 Anthropic 兼容代理/底层模型对二者的支持差异较大：
  * MiniMax-M3: 接受任何 thinking= 字段，忽略内部内容
  * DeepSeek-v4-flash (anthropic 网关): 默认就返 thinking，参数被忽略
  * 真 Anthropic 4.6+: adaptive 工作，enabled 也工作
  * 真 Anthropic 4.5-: enabled 工作，adaptive 报400
  * 真 Anthropic 4.7+: adaptive 工作，enabled 报400

策略：乐观尝试 adaptive，失败则降级 enabled，再次失败则不带 thinking。
通过 strict 的错误判定避免误吞其他 400（认证、配额、模型不存在等）。

**零模型硬编码**：根据 API 实际响应决定，不维护白名单。
"""

from typing import Any, Dict, Optional


# thinking 模式三态
THINKING_MODE_ADAPTIVE = "adaptive"  # 首选：无需 budget_tokens
THINKING_MODE_ENABLED = "enabled"    # fallback：需要 budget_tokens
THINKING_MODE_NONE = "none"          # 终极 fallback：不带 thinking

# 状态机顺序（按推荐度）
THINKING_MODE_ORDER = (THINKING_MODE_ADAPTIVE, THINKING_MODE_ENABLED, THINKING_MODE_NONE)

# 默认 budget_tokens（仅 enabled 模式使用）
# 30k 平衡了 thinking 深度与响应空间，且避开官方文档警告的 32k 警戒线
DEFAULT_BUDGET_TOKENS = 30000


def thinking_kwargs_for_mode(mode: str, budget_tokens: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """根据模式返回 ``thinking=`` 请求参数字典。

    Returns:
        dict: ``{"type": "adaptive"}`` 或 ``{"type": "enabled", "budget_tokens": N}``
        None: 模式为 ``"none"``，表示不附加 thinking 字段
    """
    if mode == THINKING_MODE_ADAPTIVE:
        return {"type": "adaptive"}
    if mode == THINKING_MODE_ENABLED:
        return {"type": "enabled", "budget_tokens": budget_tokens or DEFAULT_BUDGET_TOKENS}
    # THINKING_MODE_NONE 或其他
    return None


def next_thinking_mode(current_mode: str) -> Optional[str]:
    """状态机的下一步。

    Returns:
        下个模式；None 表示已是终态（"none"），调用方应停止并降级到不带 thinking。
    """
    try:
        idx = THINKING_MODE_ORDER.index(current_mode)
    except ValueError:
        return None
    if idx + 1 >= len(THINKING_MODE_ORDER):
        return None
    return THINKING_MODE_ORDER[idx + 1]


def is_thinking_mode_rejected(error: Exception, mode: str) -> bool:
    """严格判断：API 是否因该 thinking 模式不被支持而拒绝。

    仅当错误信息明确指向 thinking 配置时才返回 True，避免误吞：
    - 401 authentication_error（认证错误）
    - 404 model_not_found（模型不存在）
    - 429 rate_limit_exceeded（配额错误）
    - 其他通用 400

    识别场景：
    1. 官方 Anthropic 4.7+ 拒绝 enabled: ``'"thinking.type.enabled" is not supported'``
    2. 官方 Anthropic 4.5- 拒绝 adaptive: ``'"thinking.type.adaptive" is not supported'``
    3. 第三方代理拒绝整个 thinking 字段: ``'unknown field: thinking'``
    4. 通用兜底: 消息中同时出现 ``"thinking"`` 和 ``"not supported"``
       且**没有**指向其他具体 mode 名（避免误判相邻 mode 的错误）
    """
    msg = str(error).lower()

    # 1. Anthropic 官方 precise 错误格式（最可靠）
    needle = f'"thinking.type.{mode}"'
    if needle in msg:
        return True

    # 2. 若错误指向其他具体 mode 名，说明当前 mode 未被拒
    for other_mode in THINKING_MODE_ORDER:
        if other_mode == mode:
            continue
        if f'"thinking.type.{other_mode}"' in msg:
            return False

    # 3. 第三方代理 unknown field（不含具体 mode 名 → 整个 thinking 被拒）
    if "unknown" in msg and "thinking" in msg:
        return True

    # 4. 通用兜底：not supported + thinking
    if "not supported" in msg and "thinking" in msg:
        return True

    return False
