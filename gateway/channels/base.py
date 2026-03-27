"""渠道适配器基类"""

from abc import ABC, abstractmethod


class ChannelAdapter(ABC):
    """渠道适配器基类

    所有渠道适配器（飞书、iMessage、Telegram等）都应继承此类。
    """

    def __init__(self, name: str):
        self.name = name
        self.enabled = False
        self.config = {}

    @abstractmethod
    async def connect(self):
        """建立连接"""
        pass

    @abstractmethod
    async def disconnect(self):
        """断开连接"""
        pass

    @abstractmethod
    async def send_message(self, message: str, session_id: str = None):
        """发送消息"""
        pass

    @abstractmethod
    async def on_message(self, message: dict):
        """接收消息回调"""
        pass

    async def enable(self):
        """启用渠道"""
        self.enabled = True
        await self.connect()

    async def disable(self):
        """禁用渠道"""
        self.enabled = False
        await self.disconnect()

    def load_config(self, config: dict):
        """加载配置"""
        self.config = config

    def get_config(self, key: str, default=None):
        """获取配置项"""
        return self.config.get(key, default)
