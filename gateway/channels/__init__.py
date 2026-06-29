# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""FastClaw 渠道适配器

兼容性提示（Python 3.8+）:
  编写新渠道适配器时，注意 f-string 的 {} 表达式内不能包含反斜杠，
  这是 Python 3.12 才支持的特性。请将含反斜杠的表达式提取为变量再插值，
  或通过交换引号（单/双引号）来避免。详见 PEP 701。
"""

from gateway.channels.base import ChannelAdapter
from gateway.channels.feishu import FeishuAdapter, FeishuWebhookHandler
from gateway.channels.imessage import IMessageAdapter
from gateway.channels.telegram import TelegramAdapter, TelegramWebhookHandler
from gateway.channels import handlers

__all__ = [
    "ChannelAdapter",
    "FeishuAdapter",
    "FeishuWebhookHandler",
    "IMessageAdapter",
    "TelegramAdapter",
    "TelegramWebhookHandler",
    "handlers",
]
