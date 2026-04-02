# event_bus.py
"""统一事件总线 - 支持多消费者订阅"""

import asyncio
import time
import uuid
from collections import defaultdict
from typing import Dict, Set, Optional, AsyncIterator
from dataclasses import dataclass, field


@dataclass
class StreamMessage:
    message_id: str
    client_message_id: str = ""
    session_id: str = ""
    role: str = "assistant"
    event_type: str = ""
    payload: dict = field(default_factory=dict)
    timestamp: float = 0


class EventBus:
    """统一事件总线

    支持：
    - 多个消费者订阅同一个 session
    - 为每条消息生成唯一 ID
    - 通过队列异步传递事件
    """

    def __init__(self):
        self._subscribers: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        self._api = None

    def set_api(self, api):
        """设置 FastMindAPI 实例"""
        self._api = api

    def subscribe(self, session_id: str) -> asyncio.Queue:
        """订阅 session 的所有事件，返回队列"""
        queue = asyncio.Queue()
        self._subscribers[session_id].add(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue):
        """取消订阅"""
        self._subscribers[session_id].discard(queue)

    async def publish(self, session_id: str, event):
        """发布事件到所有订阅者

        Args:
            session_id: 会话 ID
            event: FastMind Event 对象
        """
        for queue in self._subscribers.get(session_id, set()):
            await queue.put(event)

    async def push(self, session_id: str, event):
        """推送事件：同时发布到订阅者，并通过 API 发送给核心处理

        Args:
            session_id: 会话 ID
            event: FastMind Event 对象
        """
        if self._api:
            await self._api.push_event(session_id, event)

    def generate_message_id(self) -> str:
        """生成唯一消息ID"""
        return f"msg_{uuid.uuid4().hex[:12]}"

    def generate_cron_id(self, task_id: str) -> str:
        """生成 cron 消息ID"""
        return f"cron_{task_id}_{int(time.time() * 1000)}"


_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """获取全局 EventBus 实例"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def set_event_bus(event_bus: EventBus):
    """设置全局 EventBus 实例"""
    global _event_bus
    _event_bus = event_bus
