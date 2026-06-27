# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""FastClaw 核心引擎"""

import sys

_IS_PACKAGE_MODE = __package__ and __package__.startswith("fastclaw.")

if _IS_PACKAGE_MODE:
    from .app import (
        app,
        start,
        SKILLS,
        load_skills,
        load_agent_config,
        load_settings,
        calculate_tokens,
        count_messages_tokens,
    )
    from .prompts import format_system_prompt, SYSTEM_PROMPT
else:
    from core.app import (
        app,
        start,
        SKILLS,
        load_skills,
        load_agent_config,
        load_settings,
        calculate_tokens,
        count_messages_tokens,
    )
    from core.prompts import format_system_prompt, SYSTEM_PROMPT

__all__ = [
    "app",
    "start",
    "SKILLS",
    "load_skills",
    "load_agent_config",
    "load_settings",
    "calculate_tokens",
    "count_messages_tokens",
    "format_system_prompt",
    "SYSTEM_PROMPT",
]
