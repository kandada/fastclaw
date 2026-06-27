# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
from datetime import datetime


async def execute(**kwargs) -> str:
    """获取当前时间"""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")
