# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""FastClaw 网关层"""

_IS_PACKAGE_MODE = __package__ and __package__.startswith("fastclaw.")

if _IS_PACKAGE_MODE:
    from .server import GatewayServer
else:
    from gateway.server import GatewayServer

__all__ = ["GatewayServer"]
