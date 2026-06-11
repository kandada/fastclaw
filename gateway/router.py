# router.py
"""FastClaw Gateway HTTP 路由"""

import asyncio
import json
import shutil
import socket
import time
import uuid
from pathlib import Path
from typing import Optional, Dict

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

_IS_PACKAGE_MODE = __package__ and __package__.startswith("fastclaw.")

if _IS_PACKAGE_MODE:
    from .event_bus import EventBus, get_event_bus, set_event_bus
    from .cron_scheduler import CronScheduler, get_cron_scheduler
    from fastclaw.core.config import (
        get_sessions_dir,
        get_settings_file,
        get_agents_dir,
        get_cron_dir,
    )
else:
    from gateway.event_bus import EventBus, get_event_bus, set_event_bus
    from gateway.cron_scheduler import CronScheduler, get_cron_scheduler
    from core.config import (
        get_sessions_dir,
        get_settings_file,
        get_agents_dir,
        get_cron_dir,
    )

router = APIRouter()

SESSION_DB_FILE = get_sessions_dir() / "sessions.json"
SETTINGS_FILE = get_settings_file()
WEBUI_DIR = Path(__file__).parent.parent / "webui"


class SessionCreate(BaseModel):
    agent_id: Optional[str] = None


class SessionUpdate(BaseModel):
    agent_id: Optional[str] = None
    name: Optional[str] = None


def ensure_sessions_db():
    """确保 sessions 数据库文件存在"""
    SESSION_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not SESSION_DB_FILE.exists():
        SESSION_DB_FILE.write_text("{}")


def load_sessions() -> dict:
    """加载 sessions"""
    ensure_sessions_db()
    try:
        return json.loads(SESSION_DB_FILE.read_text())
    except:
        time.sleep(0.05)
        try:
            return json.loads(SESSION_DB_FILE.read_text())
        except:
            return {}


def load_settings() -> dict:
    """加载设置"""
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except:
            pass
    return {"default_agent_id": "main_agent"}


def save_sessions(sessions: dict):
    """保存 sessions"""
    ensure_sessions_db()
    SESSION_DB_FILE.write_text(json.dumps(sessions, indent=2, ensure_ascii=False))


def _infer_channel(session_id: str) -> str:
    """根据 session_id 前缀推断所属渠道"""
    if not session_id:
        return "unknown"
    for prefix, channel in [("feishu_", "feishu"), ("telegram_", "telegram"),
                             ("imessage_", "imessage"), ("cli_", "cli")]:
        if session_id.startswith(prefix):
            return channel
    return "webui"


async def _load_sessions_async() -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, load_sessions)


async def _save_sessions_async(sessions: dict):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, save_sessions, sessions)


def _update_session_activity_sync(session_id: str):
    """同步更新 session 的最后活跃时间"""
    sessions = load_sessions()
    if session_id in sessions:
        sessions[session_id]["last_active_time"] = int(time.time())
        save_sessions(sessions)


def update_session_activity(session_id: str):
    """更新 session 的最后活跃时间"""
    asyncio.get_event_loop().run_in_executor(
        None, _update_session_activity_sync, session_id
    )


def validate_cron_schedule(schedule: str) -> tuple:
    """验证 cron 表达式格式

    Returns:
        (is_valid, error_message)
    """
    if not schedule or not schedule.strip():
        return False, "Schedule cannot be empty"

    parts = schedule.strip().split()
    if len(parts) != 5:
        return False, "Schedule must have 5 parts (minute, hour, day, month, weekday)"

    if all(p == "*" for p in parts):
        return False, "Schedule cannot be all '*'"

    return True, ""


def prepare_cron_task(task_data: dict) -> tuple:
    """准备并验证 cron 任务数据

    Returns:
        (prepared_task, error_message)
    """
    errors = []

    if not task_data.get("id"):
        errors.append("id")
    if not task_data.get("name"):
        errors.append("name")
    if not task_data.get("schedule"):
        errors.append("schedule")

    if errors:
        return {}, f"Missing required fields: {', '.join(errors)}"

    schedule = task_data.get("schedule", "")
    valid, msg = validate_cron_schedule(schedule)
    if not valid:
        return {}, msg

    prepared = {
        "id": task_data["id"],
        "name": task_data["name"],
        "schedule": schedule,
        "description": task_data.get("description", ""),
        "agent_id": task_data.get("agent_id", "main_agent"),
        "session_id": task_data.get("session_id"),
        "enabled": task_data.get("enabled", True),
        "last_triggered": task_data.get("last_triggered"),
    }

    return prepared, ""


@router.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok"}


@router.get("/api/skills")
async def list_skills():
    """列出所有可用技能"""
    if __package__ in (None, ""):
        from core.app import SKILLS, SKILLS_LIST
    else:
        from fastclaw.core.app import SKILLS, SKILLS_LIST

    return {
        "skills": SKILLS,
        "skills_list": SKILLS_LIST,
    }


@router.get("/api/agents")
async def list_agents():
    """列出所有 Agent"""
    agents_dir = get_agents_dir()
    agents = []
    if agents_dir.exists():
        for agent_path in agents_dir.iterdir():
            if agent_path.is_dir():
                metadata_file = agent_path / "metadata.json"
                if metadata_file.exists():
                    try:
                        agents.append(json.loads(metadata_file.read_text()))
                    except:
                        pass
    return {"agents": agents}


@router.post("/api/agents")
async def create_agent(request: Request):
    """创建新 Agent"""
    data = await request.json()
    name = data.get("name")
    if not name:
        return {"error": "Agent name is required"}, 400

    agents_dir = get_agents_dir()
    agents_dir.mkdir(parents=True, exist_ok=True)

    agent_dir = agents_dir / name
    if agent_dir.exists():
        return {"error": f"Agent '{name}' already exists"}, 400

    agent_dir.mkdir(parents=True, exist_ok=True)

    soul_content = data.get("soul_content", f"# {name}\n\nYou are a smart assistant.\n")
    soul_file = agent_dir / "SOUL.md"
    soul_file.write_text(soul_content)

    user_content = data.get("user_content", "")
    user_file = agent_dir / "USER.md"
    user_file.write_text(user_content)

    agent_content = data.get("agent_content", "")
    agent_file = agent_dir / "AGENT.md"
    agent_file.write_text(agent_content)

    metadata = {
        "name": name,
        "description": data.get("description", ""),
        "llm": data.get("llm", {}),
        "context": data.get("context", {}),
        "extra_workspaces": data.get("extra_workspaces", []),
        "created_at": int(time.time()),
    }
    metadata_file = agent_dir / "metadata.json"
    metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2))

    return metadata


@router.get("/api/agents/{name}")
async def get_agent(name: str):
    """获取 Agent 详情"""
    agent_dir = get_agents_dir() / name
    if not agent_dir.exists():
        return {"error": f"Agent '{name}' not found"}, 404

    metadata_file = agent_dir / "metadata.json"
    soul_file = agent_dir / "SOUL.md"
    user_file = agent_dir / "USER.md"
    agent_file = agent_dir / "AGENT.md"

    result = {}
    if metadata_file.exists():
        try:
            result = json.loads(metadata_file.read_text())
        except:
            pass

    if soul_file.exists():
        result["soul_content"] = soul_file.read_text()
    if user_file.exists():
        result["user_content"] = user_file.read_text()
    if agent_file.exists():
        result["agent_content"] = agent_file.read_text()

    return result


@router.put("/api/agents/{name}")
async def update_agent(name: str, request: Request):
    """更新 Agent"""
    agent_dir = get_agents_dir() / name
    if not agent_dir.exists():
        return {"error": f"Agent '{name}' not found"}, 404

    data = await request.json()

    metadata_file = agent_dir / "metadata.json"
    soul_file = agent_dir / "SOUL.md"
    user_file = agent_dir / "USER.md"
    agent_file = agent_dir / "AGENT.md"

    metadata = {}
    if metadata_file.exists():
        try:
            metadata = json.loads(metadata_file.read_text())
        except:
            pass

    if "description" in data:
        metadata["description"] = data["description"]
    if "soul_content" in data:
        soul_file.write_text(data["soul_content"])
    if "user_content" in data:
        user_file.write_text(data["user_content"])
    if "agent_content" in data:
        agent_file.write_text(data["agent_content"])
    if "llm" in data:
        metadata["llm"] = data["llm"]
    if "context" in data:
        metadata["context"] = data["context"]
    if "extra_workspaces" in data:
        metadata["extra_workspaces"] = data["extra_workspaces"]

    metadata["updated_at"] = int(time.time())
    metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2))

    return metadata


@router.delete("/api/agents/{name}")
async def delete_agent(name: str):
    """删除 Agent"""
    import shutil

    if name == "main_agent":
        return {"error": "Cannot delete main_agent"}, 400

    agent_dir = get_agents_dir() / name
    if not agent_dir.exists():
        return {"error": f"Agent '{name}' not found"}, 404

    shutil.rmtree(agent_dir)
    return {"status": "deleted"}


@router.get("/api/crons")
async def list_crons():
    """列出所有 Cron 任务"""
    tasks_file = get_cron_dir() / "tasks.json"
    if tasks_file.exists():
        try:
            return {"tasks": json.loads(tasks_file.read_text())}
        except:
            pass
    return {"tasks": []}


@router.post("/api/crons")
async def create_cron(task_data: dict):
    """创建或更新 Cron 任务"""
    prepared, error = prepare_cron_task(task_data)
    if error:
        raise HTTPException(status_code=400, detail=error)

    tasks_file = get_cron_dir() / "tasks.json"
    tasks_file.parent.mkdir(parents=True, exist_ok=True)

    tasks = []
    if tasks_file.exists():
        try:
            tasks = json.loads(tasks_file.read_text())
        except:
            pass

    task_id = prepared.get("id")
    if task_id:
        existing_idx = None
        for i, t in enumerate(tasks):
            if t.get("id") == task_id:
                existing_idx = i
                break
        if existing_idx is not None:
            existing = tasks[existing_idx]
            if "last_triggered" not in prepared or prepared["last_triggered"] is None:
                prepared["last_triggered"] = existing.get("last_triggered")
            tasks[existing_idx] = prepared
        else:
            tasks.append(prepared)
    else:
        tasks.append(prepared)

    tasks_file.write_text(json.dumps(tasks, indent=2))

    cron_scheduler = get_cron_scheduler()
    cron_scheduler.reload_tasks()

    return {"status": "created", "task": prepared}


@router.delete("/api/crons/{task_id}")
async def delete_cron(task_id: str):
    """删除 Cron 任务"""
    tasks_file = get_cron_dir() / "tasks.json"
    if tasks_file.exists():
        try:
            tasks = json.loads(tasks_file.read_text())
            tasks = [t for t in tasks if t.get("id") != task_id]
            tasks_file.write_text(json.dumps(tasks, indent=2))
            cron_scheduler = get_cron_scheduler()
            cron_scheduler.reload_tasks()
        except:
            pass
    return {"status": "deleted"}


@router.post("/api/crons/trigger")
async def trigger_cron(task_data: dict):
    """手动触发 Cron 任务"""
    global _websocket_api
    task_id = task_data.get("task_id")

    cron_scheduler = get_cron_scheduler()
    success = await cron_scheduler.trigger_task(task_id)

    if not success:
        raise HTTPException(status_code=404, detail="Task not found or disabled")

    return {"status": "triggered", "task_id": task_id}


@router.post("/api/sessions")
async def create_session(data: SessionCreate = None):
    """创建 Session"""
    sessions = await _load_sessions_async()

    import uuid

    session_id = str(uuid.uuid4())[:8]

    settings = load_settings()
    default_agent_id = settings.get("default_agent_id", "main_agent")
    agent_id = data.agent_id if data and data.agent_id else default_agent_id

    sessions[session_id] = {
        "session_id": session_id,
        "agent_id": agent_id,
        "created_at": str(Path().stat().st_mtime) if False else str(uuid.uuid4()),
        "last_active_time": int(time.time()),
        "channel": "webui",
    }

    await _save_sessions_async(sessions)

    return sessions[session_id]


@router.get("/api/sessions")
async def list_sessions():
    """列出所有 Session，自动补全 channel 字段（兼容旧记录）"""
    sessions = await _load_sessions_async()
    result = []
    for s in sessions.values():
        if "channel" not in s:
            s = dict(s)
            s["channel"] = _infer_channel(s.get("session_id", ""))
        result.append(s)
    return result


@router.get("/api/sessions/unread")
async def get_unread_counts():
    """获取所有会话的未读消息数量"""
    return {"unread_counts": _unread_counts}


@router.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """获取指定 Session"""
    sessions = await _load_sessions_async()
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return sessions[session_id]


@router.patch("/api/sessions/{session_id}")
async def update_session(session_id: str, data: SessionUpdate):
    """更新 Session"""
    sessions = await _load_sessions_async()
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    if data.agent_id:
        sessions[session_id]["agent_id"] = data.agent_id
    if data.name is not None:
        sessions[session_id]["name"] = data.name

    await _save_sessions_async(sessions)
    return sessions[session_id]


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除 Session"""
    sessions = await _load_sessions_async()
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    del sessions[session_id]
    await _save_sessions_async(sessions)

    session_dir = get_sessions_dir() / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)

    return {"status": "deleted"}


@router.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """获取 Session 的消息历史"""
    messages_file = get_sessions_dir() / session_id / "messages.jsonl"

    if not messages_file.exists():
        return []

    messages = []
    for line in messages_file.read_text().splitlines():
        if line.strip():
            try:
                messages.append(json.loads(line))
            except:
                pass

    return messages


@router.delete("/api/sessions/{session_id}/messages")
async def delete_session_messages(session_id: str):
    """清空 Session 的消息历史"""
    messages_file = get_sessions_dir() / session_id / "messages.jsonl"
    if messages_file.exists():
        messages_file.unlink()
    return {"status": "cleared"}


@router.post("/api/sessions/{session_id}/unread/clear")
async def clear_unread_count(session_id: str):
    """清除会话的未读消息数量"""
    if session_id in _unread_counts:
        _unread_counts[session_id] = 0
    return {"status": "cleared", "session_id": session_id}


@router.get("/api/settings")
async def get_settings():
    """获取系统设置"""
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except:
            pass
    return {"default_agent_id": "main_agent"}


@router.put("/api/settings")
async def update_settings(settings: dict):
    """更新系统设置"""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
    return {"status": "saved", "settings": settings}


_websocket_api = None

_cron_sse_queues: Dict[str, asyncio.Queue] = {}
_unread_counts: Dict[str, int] = {}
_pending_cron_messages: Dict[str, list] = {}
_pending_cron_info: Dict[str, dict] = {}

_event_id_to_message_id: Dict[str, str] = {}

# Per-session streaming state: {session_id: {message_id, content, thinking, role, timestamp}}
_session_stream_state: Dict[str, dict] = {}

# Per-session lock for stream consumption to prevent multiple SSE consumers from
# competing for the same session's output_queue events.
# Using per-session lock instead of a global lock allows different sessions to
# stream concurrently while still preventing race conditions when multiple SSE
# connections (e.g., multiple tabs) consume the same session's stream.
_stream_consume_locks: Dict[str, asyncio.Lock] = {}


async def get_stream_lock(session_id: str) -> asyncio.Lock:
    """Get or create a per-session lock for stream consumption."""
    if session_id not in _stream_consume_locks:
        _stream_consume_locks[session_id] = asyncio.Lock()
    return _stream_consume_locks[session_id]


def _find_latest_webui_session(sessions: dict) -> str:
    """找到最新活跃的 webui 会话 ID"""
    latest_id = None
    latest_time = 0
    for sid, s in sessions.items():
        if s.get("channel") == "webui":
            t = s.get("last_active_time", 0)
            if t > latest_time:
                latest_time = t
                latest_id = sid
    return latest_id


async def push_cron_event(session_id: str, event_data: dict):
    """推送 Cron 事件到 AI 处理，响应通过 Chat SSE 路径消费，无需阻塞"""
    print(f"[push_cron_event] session_id={session_id}, sending to AI")

    if _websocket_api is None:
        print("[push_cron_event] ERROR: _websocket_api is None!")
        return

    sessions = await _load_sessions_async()
    if not session_id or session_id not in sessions:
        fallback = _find_latest_webui_session(sessions)
        if fallback:
            print(f"[push_cron_event] session_id={session_id or 'empty'} not found in sessions, falling back to {fallback}")
            session_id = fallback
        else:
            print("[push_cron_event] no webui sessions found, using 'default'")
            session_id = "default"

    from fastmind import Event

    payload = event_data.get("payload", {})
    content = payload.get("content", "")
    task_id = payload.get("task_id", "")
    task_name = payload.get("task_name", "")
    agent_id = payload.get("agent_id", "main_agent")
    cron_id = payload.get("cron_id", "")
    trigger_time = payload.get("trigger_time", "")

    message_id = f"cron_{uuid.uuid4().hex[:12]}"

    event = Event(
        type="user.message",
        payload={
            "text": content,
            "task_id": task_id,
            "task_name": task_name,
            "agent_id": agent_id,
            "is_cron": True,
            "message_id": message_id,
            "cron_id": cron_id,
        },
        session_id=session_id,
        event_id=message_id,
    )

    _event_id_to_message_id[event.event_id] = message_id

    # Set pending cron info BEFORE pushing to engine, so chat SSE path
    # picks it up when it sees the first response event
    _pending_cron_info[session_id] = {
        "cron_id": cron_id,
        "task_id": task_id,
        "task_name": task_name,
        "trigger_time": trigger_time,
    }

    # Push to engine — chat SSE path consumes the response events
    await _websocket_api.push_event(session_id, event)

    # Send lightweight notification to cron SSE (no response events)
    if session_id not in _cron_sse_queues:
        _cron_sse_queues[session_id] = asyncio.Queue()
    await _cron_sse_queues[session_id].put(
        {
            "message_id": message_id,
            "cron_id": cron_id,
            "task_id": task_id,
            "task_name": task_name,
            "trigger_time": trigger_time,
            "events": [],
        }
    )

    _unread_counts[session_id] = _unread_counts.get(session_id, 0) + 1


def set_websocket_api(api):
    """设置 WebSocket 使用的 API 实例"""
    global _websocket_api
    _websocket_api = api
    event_bus = get_event_bus()
    event_bus.set_api(api)

    cron_scheduler = get_cron_scheduler()
    cron_scheduler.set_push_callback(push_cron_event)


class SendMessageRequest(BaseModel):
    session_id: str = "default"
    text: str


@router.post("/api/send")
async def send_message(request: SendMessageRequest):
    """发送消息（HTTP 端点，供 WebUI 使用）"""
    if _websocket_api is None:
        raise HTTPException(status_code=500, detail="API not initialized")

    from fastmind import Event

    event = Event("user.message", {"text": request.text}, request.session_id)
    await _websocket_api.push_event(request.session_id, event)

    return {"status": "sent", "session_id": request.session_id}


@router.get("/api/stream/{session_id}")
async def stream_messages(session_id: str):
    """流式获取响应（SSE 端点，供 WebUI 使用）"""

    async def event_generator():
        if _websocket_api is None:
            yield f"data: {json.dumps({'type': 'error', 'payload': {'error': 'API not initialized'}})}\n\n"
            return

        try:
            async for event in _websocket_api.stream_events(session_id):
                data = {
                    "type": event.type,
                    "payload": event.payload,
                    "session_id": event.session_id,
                }
                yield f"data: {json.dumps(data)}\n\n"
                if event.type in ("stream.end", "error"):
                    break
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'payload': {'error': str(e)}})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class ChatRequest(BaseModel):
    text: str
    client_message_id: Optional[str] = ""


@router.post("/api/chat/{session_id}")
async def chat_send_and_stream(session_id: str, request: ChatRequest):
    """发送消息，AI响应通过GET /api/chat/stream/{session_id}的SSE获取"""
    if _websocket_api is None:
        raise HTTPException(status_code=500, detail="API not initialized")

    message_id = f"msg_{uuid.uuid4().hex[:12]}"
    client_message_id = request.client_message_id or f"client_{uuid.uuid4().hex[:8]}"

    from fastmind import Event

    user_event = Event(
        type="user.message",
        payload={
            "text": request.text,
            "client_message_id": client_message_id,
            "message_id": message_id,
            "channel": "webui",
        },
        session_id=session_id,
        event_id=message_id,
    )

    _event_id_to_message_id[message_id] = message_id

    await _websocket_api.push_event(session_id, user_event)
    update_session_activity(session_id)

    return {"status": "ok", "message_id": message_id}


@router.post("/api/chat/stop/{session_id}")
async def chat_stop(session_id: str):
    """停止当前会话的 AI 响应"""
    if _websocket_api is None:
        raise HTTPException(status_code=500, detail="API not initialized")

    session = _websocket_api.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await session.stop()
    _session_stream_state.pop(session_id, None)
    return {"status": "stopped", "session_id": session_id}


@router.get("/api/chat/state/{session_id}")
async def chat_stream_state(session_id: str):
    """获取当前会话的流式输出状态，用于前端切换回会话时恢复显示"""
    state = _session_stream_state.get(session_id)
    if state:
        return state
    return {
        "message_id": None,
        "content": "",
        "thinking": "",
        "role": "assistant",
        "timestamp": 0,
    }


async def _stream_session_events(session, poll_interval=15.0):
    """Stream session events with configurable poll interval.

    Like FastMindAPI.stream_events() but with adjustable idle poll timeout
    to reduce CPU usage. Yields None when a poll cycle finds no new events,
    allowing the SSE generator to emit heartbeats without CancelledError overhead.
    """
    cursor = session._event_buffer.tail_cursor
    while session.is_alive:
        try:
            events = await session._event_buffer.wait(cursor, timeout=poll_interval)
            if not events:
                yield None
                continue
            cursor += len(events)
            for event in events:
                yield event
                if event.type in ("stream.end", "error", "interrupt"):
                    return
        except asyncio.CancelledError:
            break
    return


@router.get("/api/chat/stream/{session_id}")
async def chat_stream_subscribe(session_id: str):
    """订阅 SSE 流

    用于接收 AI 响应。
    注意：Cron 消息请使用 /api/cron/stream/{session_id}
    """
    if _websocket_api is None:
        raise HTTPException(status_code=500, detail="API not initialized")

    async def sse_generator():
        try:
            yield f"event: connected\n"
            yield f"data: {{}}\n\n"

            session = _websocket_api.get_session(session_id)
            if not session:
                yield f"event: session_waiting\n"
                yield f"data: {json.dumps({'message': 'Waiting for session...'})}\n\n"

                for i in range(60):
                    await asyncio.sleep(1)
                    session = _websocket_api.get_session(session_id)
                    if session:
                        break

                if not session:
                    yield f"event: session_timeout\n"
                    yield f"data: {json.dumps({'message': 'Session timeout'})}\n\n"
                    return

            try:
                iterator = _stream_session_events(session, poll_interval=15.0).__aiter__()
                heartbeat_interval_polls = 2
                heartbeat_counter = 0
                max_empty_polls = 480 * heartbeat_interval_polls
                message_started = False
                current_msg_id = None  # Keep same msg_id for all chunks in a message
                _session_restart_polls = 0
                while True:
                    try:
                        event = await iterator.__anext__()
                        _session_restart_polls = 0
                    except StopAsyncIteration:
                        if not session.is_alive:
                            _session_restart_polls += 1
                            if _session_restart_polls >= 6:
                                break
                            await asyncio.sleep(0.5)
                        iterator = _stream_session_events(
                            session, poll_interval=15.0
                        ).__aiter__()
                        continue

                    if event is None:
                        heartbeat_counter += 1
                        if heartbeat_counter >= max_empty_polls:
                            yield f"event: error\n"
                            yield f"data: {json.dumps({'error': 'Stream timeout'})}\n\n"
                            break
                        if heartbeat_counter % heartbeat_interval_polls == 0:
                            yield f": heartbeat\n\n"
                        continue

                    heartbeat_counter = 0
                    if event.type == "cron.message":
                        continue

                    # Only compute msg_id if we don't have one yet
                    if current_msg_id is None:
                        current_msg_id = event.payload.get("message_id")
                        if not current_msg_id:
                            current_msg_id = (
                                f"evt_{event.event_id[:8]}"
                                if event.event_id
                                else f"unk_{time.time()}"
                            )

                    # Emit message.start for the first chunk event
                    if (
                        event.type in ("stream.chunk", "stream.thinking")
                        and not message_started
                    ):
                        start_data = {
                            'role': 'assistant',
                            'timestamp': time.time(),
                        }
                        # Check if this message is from a cron-triggered response
                        cron_info = _pending_cron_info.pop(session_id, None)
                        if cron_info:
                            start_data['isCron'] = True
                            start_data['taskName'] = cron_info['task_name']
                            start_data['taskId'] = cron_info['task_id']
                            start_data['triggerTime'] = cron_info['trigger_time']
                        yield f"id: {current_msg_id}\n"
                        yield f"event: message.start\n"
                        yield f"data: {json.dumps(start_data)}\n\n"
                        _session_stream_state[session_id] = {
                            "message_id": current_msg_id,
                            "content": "",
                            "thinking": "",
                            "role": "assistant",
                            "timestamp": time.time(),
                        }
                        message_started = True

                    sse_event = _transform_event_to_sse(event, current_msg_id)
                    if sse_event is None:
                        continue

                    # Immediately yield SSE event without buffering
                    yield f"id: {sse_event['id']}\n"
                    yield f"event: {sse_event['event']}\n"
                    yield f"data: {json.dumps(sse_event['data'])}\n\n"

                    # Update state for session recovery
                    if session_id in _session_stream_state:
                        if sse_event["event"] == "message.chunk":
                            _session_stream_state[session_id]["content"] += (
                                sse_event["data"].get("delta", "")
                            )
                        elif sse_event["event"] == "message.thinking":
                            _session_stream_state[session_id]["thinking"] += (
                                sse_event["data"].get("delta", "")
                            )

                    if sse_event["event"] in ("message.end", "error"):
                        _session_stream_state.pop(session_id, None)
                        message_started = False
                        current_msg_id = None  # Reset for next message
                        heartbeat_counter = 0  # Reset heartbeat for next message
                        if sse_event["event"] == "error":
                            break  # Exit loop on error
            except asyncio.CancelledError:
                pass
            except Exception as e:
                yield f"event: error\n"
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                return

            if not session.is_alive:
                yield f"event: session_stopped\n"
                yield f"data: {{}}\n\n"

        except asyncio.CancelledError:
            pass
        except Exception as e:
            yield f"event: error\n"
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/cron/stream/{session_id}")
async def cron_stream_subscribe(session_id: str):
    """订阅 Cron 消息 SSE 流

    用于接收定时任务的推送消息和 AI 响应。
    """
    if session_id not in _cron_sse_queues:
        _cron_sse_queues[session_id] = asyncio.Queue()

    queue = _cron_sse_queues[session_id]

    async def sse_generator():
        try:
            print(f"[cron_stream] SSE connection opened for session {session_id}")
            yield f"event: connected\n"
            yield f"data: {{}}\n\n"

            while True:
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=30)
                    message_id = event_data.get("message_id", "")
                    cron_id = event_data.get("cron_id", "")
                    task_id = event_data.get("task_id", "unknown")
                    task_name = event_data.get("task_name", "unknown")
                    trigger_time = event_data.get("trigger_time", "")
                    collected_events = event_data.get("events", [])

                    print(
                        f"[cron_stream] Received cron data: message_id={message_id}, cron_id={cron_id}, events_count={len(collected_events)}"
                    )

                    yield f"id: {cron_id}\n"
                    yield f"event: cron.message\n"
                    yield f"data: {json.dumps({'message_id': message_id, 'task_id': task_id, 'task_name': task_name, 'content': '', 'cron_id': cron_id, 'trigger_time': trigger_time})}\n\n"

                    for stream_event in collected_events:
                        sse_event = _transform_event_to_sse(stream_event, message_id)
                        if sse_event is None:
                            continue
                        print(
                            f"[cron_stream] Yielding event: type={sse_event['event']}, id={sse_event['id']}"
                        )
                        yield f"id: {sse_event['id']}\n"
                        yield f"event: {sse_event['event']}\n"
                        yield f"data: {json.dumps(sse_event['data'])}\n\n"

                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"

        except asyncio.CancelledError:
            pass
        except Exception as e:
            yield f"event: error\n"
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _transform_event_to_sse(event, target_message_id: str = None) -> Optional[dict]:
    """将 FastMind Event 转换为 SSE 事件"""
    event_map = {
        "stream.chunk": "message.chunk",
        "stream.thinking": "message.thinking",
        "stream.tool_start": "message.tool_start",
        "stream.fragment": "message.tool_start",
        "stream.end": "message.end",
        "stream.error": "error",
        "cron.message": "cron.message",
        "user.message": None,
    }

    sse_event_type = event_map.get(event.type)
    if sse_event_type is None:
        return None

    if event.type == "cron.message":
        msg_id = target_message_id or f"cron_{event.payload.get('task_id', 'unknown')}"
    elif target_message_id:
        msg_id = target_message_id
    else:
        msg_id = event.payload.get("message_id", "unknown")

    if sse_event_type == "message.tool_start":
        tool_calls = event.payload.get("tool_calls", [])
        tool_info_parts = []
        for tc in tool_calls:
            func_name = tc.get("function", {}).get("name", "unknown")
            args_str = tc.get("function", {}).get("arguments", "")
            try:
                args_obj = json.loads(args_str) if args_str else {}
                if isinstance(args_obj, dict):
                    first_arg = next(
                        iter(args_obj.values()), args_str[:50] if args_str else ""
                    )
                else:
                    first_arg = str(args_obj)[:50] if args_str else ""
            except:
                first_arg = args_str[:50] if args_str else ""
            tool_info_parts.append(
                f"{func_name}({first_arg})" if first_arg else func_name
            )
        tool_info_str = (
            "[Executing tool: " + " | ".join(tool_info_parts) + "]"
            if tool_info_parts
            else "[Executing tool...]"
        )
        data = {
            "tool_calls": tool_calls,
            "tool_info": tool_info_str,
        }
    elif sse_event_type == "error":
        data = {"error": event.payload.get("error", "unknown error")}
    else:
        data = event.payload

    return {"id": msg_id, "event": sse_event_type, "data": data}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, session_id: str = None):
    """WebSocket 端点

    Args:
        session_id: 可选的 query 参数，优先于消息中的 session_id
    """
    if _websocket_api is None:
        await websocket.close(code=1011, reason="API not initialized")
        return

    await websocket.accept()

    active_session_id = session_id or "default"

    try:
        consumer_task = None

        async def consume_events():
            nonlocal consumer_task
            try:
                async for event in _websocket_api.stream_events(active_session_id):
                    if event.type == "stream.fragment" and event.payload.get(
                        "has_tool_calls"
                    ):
                        tool_calls = event.payload.get("tool_calls", [])
                        tool_info_parts = []
                        for tc in tool_calls:
                            func_name = tc.get("function", {}).get("name", "unknown")
                            args_str = tc.get("function", {}).get("arguments", "")
                            try:
                                args_obj = json.loads(args_str) if args_str else {}
                                if isinstance(args_obj, dict):
                                    first_arg = next(
                                        iter(args_obj.values()),
                                        args_str[:50] if args_str else "",
                                    )
                                else:
                                    first_arg = str(args_obj)[:50] if args_str else ""
                            except:
                                first_arg = args_str[:50] if args_str else ""
                            tool_info_parts.append(
                                f"{func_name}({first_arg})" if first_arg else func_name
                            )
                        tool_info_str = (
                            "[Executing tool: " + " | ".join(tool_info_parts) + "]"
                            if tool_info_parts
                            else "[Executing tool...]"
                        )

                        await websocket.send_json(
                            {
                                "type": "stream.tool_start",
                                "payload": {
                                    "tool_calls": tool_calls,
                                    "tool_info": tool_info_str,
                                },
                                "session_id": event.session_id,
                            }
                        )
                        await asyncio.sleep(0)
                        continue

                    data = {
                        "type": event.type,
                        "payload": event.payload,
                        "session_id": event.session_id,
                    }
                    await websocket.send_json(data)
                    await asyncio.sleep(0)
                    if event.type in ("stream.end", "error"):
                        consumer_task = None
                        break
            except Exception as e:
                print(f"Error consuming events: {e}")
                consumer_task = None

        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)

                event_type = message.get("type", "user.message")
                payload = message.get("payload", {})
                msg_session_id = message.get("session_id")

                effective_session_id = (
                    session_id if session_id else (msg_session_id or "default")
                )

                update_session_activity(effective_session_id)

                from fastmind import Event

                event = Event(event_type, payload, effective_session_id)
                await _websocket_api.push_event(effective_session_id, event)

                if consumer_task is None:
                    active_session_id = effective_session_id
                    consumer_task = asyncio.create_task(consume_events())

            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "payload": {"error": "Invalid JSON"},
                        "session_id": active_session_id,
                    }
                )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        if consumer_task:
            consumer_task.cancel()
