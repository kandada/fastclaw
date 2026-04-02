# cron_scheduler.py
"""Cron 调度器 - 网关层的定时任务管理"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Set, Optional, Callable, Awaitable
from dataclasses import dataclass
import croniter


@dataclass
class CronTask:
    id: str
    name: str
    schedule: str
    description: str
    agent_id: str
    session_id: str
    enabled: bool


@dataclass
class QueuedMessage:
    task_id: str
    task_name: str
    content: str
    agent_id: str
    session_id: str
    cron_id: str
    trigger_time: str
    is_cron: bool = True


class CronScheduler:
    """Cron 调度器

    职责：
    - 管理定时任务的加载和调度
    - 支持手动触发和自动触发
    - 通过回调机制将消息推送到 SSE
    - 消息队列确保按顺序发送
    """

    def __init__(self):
        self._tasks: Dict[str, CronTask] = {}
        self._queues: Dict[str, asyncio.Queue] = {}
        self._processing: Dict[str, bool] = {}
        self._push_callback: Optional[Callable[[str, dict], Awaitable[None]]] = None
        self._task_file = Path("workspace/data/cron/tasks.json")
        self._running = False
        self._runner_task: Optional[asyncio.Task] = None

    def set_push_callback(self, callback: Callable[[str, dict], Awaitable[None]]):
        """设置推送回调，用于通过 SSE 推送消息

        Args:
            callback: async function(session_id, event_data)
        """
        self._push_callback = callback

    def load_tasks(self):
        """从文件加载定时任务"""
        if not self._task_file.exists():
            self._tasks = {}
            return

        try:
            tasks_data = json.loads(self._task_file.read_text())
            self._tasks = {}
            for t in tasks_data:
                task = CronTask(
                    id=t.get("id", ""),
                    name=t.get("name", ""),
                    schedule=t.get("schedule", ""),
                    description=t.get("description", ""),
                    agent_id=t.get("agent_id", "main_agent"),
                    session_id=t.get("session_id", "default"),
                    enabled=t.get("enabled", True),
                )
                self._tasks[task.id] = task
        except Exception as e:
            print(f"Failed to load cron tasks: {e}")
            self._tasks = {}

    def save_tasks(self):
        """保存定时任务到文件"""
        self._task_file.parent.mkdir(parents=True, exist_ok=True)
        tasks_data = []
        for task in self._tasks.values():
            tasks_data.append(
                {
                    "id": task.id,
                    "name": task.name,
                    "schedule": task.schedule,
                    "description": task.description,
                    "agent_id": task.agent_id,
                    "session_id": task.session_id,
                    "enabled": task.enabled,
                }
            )
        self._task_file.write_text(json.dumps(tasks_data, indent=2, ensure_ascii=False))

    def get_task(self, task_id: str) -> Optional[CronTask]:
        """获取任务"""
        return self._tasks.get(task_id)

    def list_tasks(self) -> list:
        """列出所有任务"""
        return list(self._tasks.values())

    async def trigger_task(self, task_id: str) -> bool:
        """手动触发一个任务

        Args:
            task_id: 任务 ID

        Returns:
            是否成功触发
        """
        task = self._tasks.get(task_id)
        if not task:
            return False

        if not task.enabled:
            return False

        await self._enqueue_message(task)
        return True

    async def _enqueue_message(self, task: CronTask):
        """将任务消息加入队列"""
        session_id = task.session_id or "default"
        cron_id = f"cron_{task.id}_{int(time.time() * 1000)}"
        trigger_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        content = f"{task.description}\n[Cron Task: {task.name}]\nTrigger time: {trigger_time}"

        queued_msg = QueuedMessage(
            task_id=task.id,
            task_name=task.name,
            content=content,
            agent_id=task.agent_id,
            session_id=session_id,
            cron_id=cron_id,
            trigger_time=trigger_time,
            is_cron=True,
        )

        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue()

        await self._queues[session_id].put(queued_msg)

        if not self._processing.get(session_id, False):
            asyncio.create_task(self._process_queue(session_id))

    async def _process_queue(self, session_id: str):
        """处理消息队列"""
        self._processing[session_id] = True

        while True:
            queue = self._queues.get(session_id)
            if not queue or queue.empty():
                break

            msg: QueuedMessage = await queue.get()

            if self._push_callback:
                event_data = {
                    "type": "cron.message",
                    "payload": {
                        "task_id": msg.task_id,
                        "task_name": msg.task_name,
                        "content": msg.content,
                        "cron_id": msg.cron_id,
                        "trigger_time": msg.trigger_time,
                        "agent_id": msg.agent_id,
                    },
                }
                print(
                    f"[CronScheduler] Pushing cron event to session {session_id}: {msg.task_name}"
                )
                await self._push_callback(session_id, event_data)

            await asyncio.sleep(0.1)

        self._processing[session_id] = False

    async def _check_and_trigger(self):
        """检查所有任务是否应该触发"""
        now = datetime.now()

        for task in self._tasks.values():
            if not task.enabled:
                continue

            try:
                cron = croniter.croniter(task.schedule, now - timedelta(seconds=60))
                next_run = cron.get_next(datetime)
                prev_run = cron.get_prev(datetime)

                time_diff = abs((now - prev_run).total_seconds())

                if time_diff < 70:
                    print(f"Cron task '{task.name}' triggered at {now}")
                    await self._enqueue_message(task)

            except Exception as e:
                print(f"Error checking cron task '{task.name}': {e}")

    async def start(self):
        """启动调度器"""
        if self._running:
            return

        self._running = True
        self.load_tasks()
        self._runner_task = asyncio.create_task(self._run_loop())
        print("CronScheduler started")

    async def stop(self):
        """停止调度器"""
        self._running = False
        if self._runner_task:
            self._runner_task.cancel()
            try:
                await self._runner_task
            except asyncio.CancelledError:
                pass
        print("CronScheduler stopped")

    async def _run_loop(self):
        """运行调度循环"""
        while self._running:
            try:
                await self._check_and_trigger()
            except Exception as e:
                print(f"Error in cron scheduler loop: {e}")

            await asyncio.sleep(60)

    def reload_tasks(self):
        """重新加载任务（外部调用）"""
        self.load_tasks()


_cron_scheduler: Optional[CronScheduler] = None


def get_cron_scheduler() -> CronScheduler:
    """获取全局 CronScheduler 实例"""
    global _cron_scheduler
    if _cron_scheduler is None:
        _cron_scheduler = CronScheduler()
    return _cron_scheduler
