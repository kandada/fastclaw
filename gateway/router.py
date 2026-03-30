# router.py
"""FastClaw Gateway HTTP 路由"""

import asyncio
import json
import shutil
import socket
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

router = APIRouter()

SESSION_DB_FILE = Path("workspace/data/sessions/sessions.json")
SETTINGS_FILE = Path("workspace/data/settings.json")
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


@router.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok"}


@router.get("/api/skills")
async def list_skills():
    """列出所有可用技能"""
    from core.app import SKILLS, SKILLS_LIST

    return {
        "skills": SKILLS,
        "skills_list": SKILLS_LIST,
    }


@router.get("/api/agents")
async def list_agents():
    """列出所有 Agent"""
    agents_dir = Path("workspace/data/agents")
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

    agents_dir = Path("workspace/data/agents")
    agents_dir.mkdir(parents=True, exist_ok=True)

    agent_dir = agents_dir / name
    if agent_dir.exists():
        return {"error": f"Agent '{name}' already exists"}, 400

    agent_dir.mkdir(parents=True, exist_ok=True)

    soul_content = data.get("soul_content", f"# {name}\n\n你是一个智能助手。\n")
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
    agent_dir = Path(f"workspace/data/agents/{name}")
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
    agent_dir = Path(f"workspace/data/agents/{name}")
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

    agent_dir = Path(f"workspace/data/agents/{name}")
    if not agent_dir.exists():
        return {"error": f"Agent '{name}' not found"}, 404

    shutil.rmtree(agent_dir)
    return {"status": "deleted"}


@router.get("/api/crons")
async def list_crons():
    """列出所有 Cron 任务"""
    tasks_file = Path("workspace/data/cron/tasks.json")
    if tasks_file.exists():
        try:
            return {"tasks": json.loads(tasks_file.read_text())}
        except:
            pass
    return {"tasks": []}


@router.post("/api/crons")
async def create_cron(task_data: dict):
    """创建或更新 Cron 任务"""
    tasks_file = Path("workspace/data/cron/tasks.json")
    tasks_file.parent.mkdir(parents=True, exist_ok=True)

    tasks = []
    if tasks_file.exists():
        try:
            tasks = json.loads(tasks_file.read_text())
        except:
            pass

    task_id = task_data.get("id")
    if task_id:
        existing_idx = None
        for i, t in enumerate(tasks):
            if t.get("id") == task_id:
                existing_idx = i
                break
        if existing_idx is not None:
            tasks[existing_idx] = task_data
        else:
            tasks.append(task_data)
    else:
        tasks.append(task_data)

    tasks_file.write_text(json.dumps(tasks, indent=2))
    return {"status": "created", "task": task_data}


@router.delete("/api/crons/{task_id}")
async def delete_cron(task_id: str):
    """删除 Cron 任务"""
    tasks_file = Path("workspace/data/cron/tasks.json")
    if tasks_file.exists():
        try:
            tasks = json.loads(tasks_file.read_text())
            tasks = [t for t in tasks if t.get("id") != task_id]
            tasks_file.write_text(json.dumps(tasks, indent=2))
        except:
            pass
    return {"status": "deleted"}


@router.post("/api/crons/trigger")
async def trigger_cron(task_data: dict):
    """手动触发 Cron 任务"""
    global _websocket_api
    task_id = task_data.get("task_id")

    if _websocket_api is None:
        raise HTTPException(status_code=500, detail="API not initialized")

    tasks_file = Path("workspace/data/cron/tasks.json")
    task = None
    if tasks_file.exists():
        try:
            tasks = json.loads(tasks_file.read_text())
            for t in tasks:
                if t.get("id") == task_id:
                    task = t
                    break
        except:
            pass

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    from fastmind import Event

    session_id = task.get("session_id") or "default"
    description = task.get("description", "")
    event = Event(
        type="cron.triggered",
        payload={
            "task_id": task["id"],
            "task_name": task.get("name", ""),
            "text": description,
            "description": description,
            "agent_id": task.get("agent_id", "main_agent"),
        },
        session_id=session_id,
    )
    await _websocket_api.push_event(session_id, event)

    return {"status": "triggered", "task_id": task_id}


@router.post("/api/sessions")
async def create_session(data: SessionCreate = None):
    """创建 Session"""
    sessions = load_sessions()

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
    }

    save_sessions(sessions)

    return sessions[session_id]


@router.get("/api/sessions")
async def list_sessions():
    """列出所有 Session"""
    sessions = load_sessions()
    return list(sessions.values())


@router.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """获取指定 Session"""
    sessions = load_sessions()
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return sessions[session_id]


@router.patch("/api/sessions/{session_id}")
async def update_session(session_id: str, data: SessionUpdate):
    """更新 Session"""
    sessions = load_sessions()
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    if data.agent_id:
        sessions[session_id]["agent_id"] = data.agent_id
    if data.name is not None:
        sessions[session_id]["name"] = data.name

    save_sessions(sessions)
    return sessions[session_id]


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除 Session"""
    sessions = load_sessions()
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    del sessions[session_id]
    save_sessions(sessions)

    session_dir = Path(f"workspace/data/sessions/{session_id}")
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)

    return {"status": "deleted"}


@router.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """获取 Session 的消息历史"""
    messages_file = Path(f"workspace/data/sessions/{session_id}/messages.jsonl")

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
    messages_file = Path(f"workspace/data/sessions/{session_id}/messages.jsonl")
    if messages_file.exists():
        messages_file.unlink()
    return {"status": "cleared"}


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


def set_websocket_api(api):
    """设置 WebSocket 使用的 API 实例"""
    global _websocket_api
    _websocket_api = api


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
                            "[执行工具: " + " | ".join(tool_info_parts) + "]"
                            if tool_info_parts
                            else "[正在执行工具...]"
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
