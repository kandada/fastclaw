# API 参考

## 基础信息

- Base URL: `http://localhost:8765`
- WebSocket: `ws://localhost:8765/ws`

## REST API

### 健康检查

```
GET /api/health
```

返回：
```json
{"status": "ok"}
```

### 会话管理

#### 列出所有会话

```
GET /api/sessions
```

#### 创建会话

```
POST /api/sessions
```

#### 获取会话消息

```
GET /api/sessions/{session_id}/messages
```

#### 删除会话

```
DELETE /api/sessions/{session_id}
```

### 技能管理

#### 列出所有技能

```
GET /api/skills
```

返回：
```json
{
  "skills": {
    "current_time": {
      "name": "current_time",
      "description": "获取当前日期和时间",
      "path": "workspace/skills/bundled/current_time"
    }
  }
}
```

### Agent 管理

#### 列出所有 Agent

```
GET /api/agents
```

### 定时任务

#### 列出所有任务

```
GET /api/crons
```

#### 创建任务

```
POST /api/crons
Content-Type: application/json

{
  "name": "每天早安",
  "schedule": "0 9 * * *",
  "description": "给我一个问候",
  "agent_id": "main_agent",
  "session_id": "default",
  "enabled": true
}
```

#### 删除任务

```
DELETE /api/crons/{task_id}
```

#### 手动触发任务

```
POST /api/crons/trigger
Content-Type: application/json

{"task_id": "task_xxx"}
```

## WebSocket API

### 连接

```
WS /ws?session_id={session_id}
```

### 发送消息

```json
{
  "type": "user.message",
  "payload": {"text": "你好"},
  "session_id": "xxx"
}
```

### 接收事件

| 事件类型 | 说明 |
|----------|------|
| `stream.chunk` | 流式输出片段 |
| `stream.tool_start` | 开始执行工具 |
| `stream.end` | 输出结束 |
| `stream.error` | 错误信息 |

#### stream.chunk

```json
{
  "type": "stream.chunk",
  "payload": {"delta": "你好"},
  "session_id": "xxx"
}
```

#### stream.tool_start

```json
{
  "type": "stream.tool_start",
  "payload": {
    "tool_calls": [...],
    "tool_info": "[执行工具: run_skills(current_time)]"
  },
  "session_id": "xxx"
}
```
