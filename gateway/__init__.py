"""FastClaw 网关层"""

_IS_PACKAGE_MODE = __package__ and __package__.startswith("fastclaw.")

if _IS_PACKAGE_MODE:
    from .server import GatewayServer
else:
    from gateway.server import GatewayServer

__all__ = ["GatewayServer"]
