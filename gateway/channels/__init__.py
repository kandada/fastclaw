# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""FastClaw 渠道适配器"""

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
