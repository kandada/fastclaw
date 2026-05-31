# SSE API 参考

FastClaw 采用 **POST 发送消息 + SSE 接收流式回复** 的双通道架构。SSE 连接为长连接，跨多条消息复用，无须每次发言重新握手。

## 架构概览

```
Client                         FastClaw Server (localhost:8765)
  │                                      │
  ├─ GET /api/chat/stream/{id} ──────────→  建立 SSE 长连接
  │  ←─── event: connected ─────────────┤
  │                                      │
  ├─ POST /api/chat/{id} ───────────────→  发送消息
  │  ←─── {"status":"ok"} ──────────────┤
  │                                      │
  │  ←─── event: message.start ─────────┤  AI 开始回复
  │  ←─── event: message.thinking ──────┤  思考过程（推理模型）
  │  ←─── event: message.chunk ─────────┤  回复文本片段
  │  ←─── event: message.chunk ─────────┤
  │  ←─── event: message.tool_start ────┤  工具调用（如有）
  │  ←─── event: message.end ───────────┤  回复结束
  │                                      │
  ├─ POST /api/chat/{id} ───────────────→  发送第二条消息
  │  ←─── {"status":"ok"} ──────────────┤  （SSE 复用同一连接）
  │  ←─── event: message.start ─────────┤
  │  ...                                 │
```

## 快速开始（curl 两条终端）

**终端 A** — 创建会话并建立 SSE 长连接：

```bash
# 1. 创建会话
SESSION=$(curl -s -X POST http://localhost:8765/api/sessions \
  -H 'Content-Type: application/json' \
  -d '{"agent_id":"main_agent"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
echo "Session: $SESSION"

# 2. 建立 SSE 连接，持续监听
curl -s -N "http://localhost:8765/api/chat/stream/$SESSION"
```

**终端 B** — 发送消息：

```bash
SESSION="替换为上面的 session_id"

# 发送消息
curl -s -X POST "http://localhost:8765/api/chat/$SESSION" \
  -H 'Content-Type: application/json' \
  -d '{"text": "你好，请用一句话介绍你自己"}'
```

终端 A 会实时看到 SSE 事件流。

---

## 发送消息

### POST /api/chat/{session_id}

```
POST http://localhost:8765/api/chat/{session_id}
Content-Type: application/json
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `text` | string | 是 | 用户输入的消息内容 |
| `client_message_id` | string | 否 | 客户端消息 ID，用于去重/幂等。不传则自动生成 |

```json
{
  "text": "帮我查一下当前时间",
  "client_message_id": "client_abc123"
}
```

**响应：**

```json
{
  "status": "ok",
  "message_id": "msg_966f9cca494b"
}
```

- 响应立即返回（`text` 被推入引擎异步处理），AI 回复通过 SSE 流获取
- 如果 session 不存在，**自动创建**；但建议先显式 `POST /api/sessions` 创建
- `message_id` 是服务端生成的唯一消息 ID

---

## 接收消息（SSE 流）

### GET /api/chat/stream/{session_id}

```
GET http://localhost:8765/api/chat/stream/{session_id}
Accept: text/event-stream
```

**连接行为：**

- 返回 `text/event-stream`，持续推送直到连接关闭
- **长连接复用**：一条消息回复结束后连接不断开，继续等待下一条消息的回复
- **心跳**：每 30s 无数据时发送 `: heartbeat\n\n`（SSE 注释，浏览器静默忽略）
- **闲置超时**：连续 480 次心跳（约 4 小时）无消息则断开

**SSE 响应头：**

```
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

### SSE 事件参考

#### message.start — 回复开始

每轮 AI 回复开始时发送，包含 timing/role 等元信息。

```
event: message.start
data: {"role":"assistant","timestamp":1780150094.123}
```

如果是 Cron 定时任务触发，额外包含：

```json
{
  "role": "assistant",
  "timestamp": 1780150094.123,
  "isCron": true,
  "taskName": "每日早安",
  "taskId": "task_abc",
  "triggerTime": "2026-05-30 09:00:00"
}
```

#### message.thinking — 思考过程

仅推理模型（DeepSeek-R1 等）发送，包含模型的内部推理链。

```
event: message.thinking
data: {"delta":"用户想查询当前时间，我应该调用工具..."}
```

每个 `delta` 是一个增量文本片段，客户端应累加拼接。

#### message.chunk — 回复文本

AI 回复的主体内容，逐 token 流式推送。

```
event: message.chunk
data: {"delta":"你好"}
```

```
event: message.chunk
data: {"delta":"！当"}
```

```
event: message.chunk
data: {"delta":"前时间是"}
```

> 拼接方式：`full_content += delta`，所有 chunk 的 delta 按序拼接即为完整回复。

#### message.tool_start — 工具执行

AI 决定调用工具（如执行 shell 命令、查询技能）时发送。

```
event: message.tool_start
data: {
  "tool_calls": [
    {
      "function": {
        "name": "run_skills",
        "arguments": "{\"skill_name\": \"current_time\"}"
      }
    }
  ],
  "tool_info": "[执行工具: run_skills(current_time)]"
}
```

| 字段 | 说明 |
|------|------|
| `tool_calls` | 原始 tool_calls 数组 |
| `tool_info` | 人类可读的工具调用摘要 |

`message.tool_start` 之后通常还会有一轮 `message.start` → `message.chunk` → `message.end`（工具执行后 AI 再次回复）。

#### message.end — 回复结束

一条完整的 AI 回复结束时发送。

```
event: message.end
data: {}
```

客户端应在收到 `message.end` 后：
- 标记该条消息为已完成
- 停止累加 `chunk` / `thinking`
- 触发后续 UI 更新（如刷新会话列表）

#### error — 错误

```
event: error
data: {"error": "Stream timeout"}
```

#### 心跳

```
: heartbeat

```

以 `:` 开头的 SSE 注释行，可忽略。

---

## 停止生成

停止当前正在进行的 AI 回复。适用于用户点击"停止"按钮、超时中断、或客户端主动取消等场景。

### POST /api/chat/stop/{session_id}

```
POST http://localhost:8765/api/chat/stop/{session_id}
```

**请求体**：无。

**成功响应** (200)：

```json
{"status": "stopped", "session_id": "abc123"}
```

**错误响应**：

| 状态码 | 含义 |
|--------|------|
| `404` | 会话不存在 `{"detail":"Session not found"}` |
| `500` | 服务未初始化 `{"detail":"API not initialized"}` |

### 调用流程

```
Client                              Server
  │                                    │
  │  ① EventSource.close()            │  客户端先断开 SSE
  │                                    │
  │  ② POST /api/chat/stop/{id} ────→ │  请求停止
  │  ←─── {"status":"stopped"} ────── │  引擎停止、stream_state 清空
  │                                    │
  │  ③（如有需要）重新建立 SSE        │  下一次发消息前正常 connect 即可
```

**关键时序**：必须在 POST 停止请求**之前**先关闭本地 SSE 连接（`EventSource.close()`）。

原因：
- `POST /stop` 调用 `session.stop()`，session 变为 `is_alive=false`
- 如果 SSE 还连着，后端检测到 `is_alive=false` 后会发送 `session_stopped` 事件
- 如果客户端没有提前 `close()`，`session_stopped` 事件可能触发 `onerror` 而非正常的停止逻辑

### SSE 侧行为

调用 stop 后，已存在的 SSE 连接会收到：

```
event: session_stopped
data: {}
```

然后连接关闭。此时 `isSending` 和 `isStreaming` 应重置为 `false`，UI 恢复为可输入状态。

### 代码示例

**Python：**

```python
import requests

def stop_generation(session_id: str):
    """停止正在进行的 AI 生成"""
    resp = requests.post(
        f"http://localhost:8765/api/chat/stop/{session_id}"
    )
    if resp.status_code == 200:
        print(f"已停止: {resp.json()}")
    elif resp.status_code == 404:
        print("会话不存在")
    else:
        print(f"停止失败: {resp.text}")
```

**JavaScript（完整模式）：**

```javascript
async function stopGeneration(sessionId, eventSource) {
  // 1. 先关闭本地 SSE 连接
  if (eventSource) {
    eventSource.close();
  }

  // 2. 请求服务端停止
  try {
    const resp = await fetch(`/api/chat/stop/${sessionId}`, {
      method: "POST",
    });
    const data = await resp.json();
    console.log("已停止:", data);
  } catch (e) {
    console.error("停止请求失败:", e);
  }

  // 3. 重置前端状态
  isStreaming = false;
  isSending = false;
}
```

**curl：**

```bash
curl -s -X POST "http://localhost:8765/api/chat/stop/{session_id}"
# → {"status":"stopped","session_id":"abc123"}
```

### 停止后的状态

- `_session_stream_state` 被清空（`/api/chat/state/{id}` 将返回空快照）
- session 的 `is_alive` 变为 `false`
- 已有 SSE 连接关闭，前端需要重建 SSE 才能接收下一条消息的回复
- 已接收的 `message.chunk` 内容保留在 messages 数组中（不会丢失）

### 注意事项

1. **重复停止无害** — 对已经停止的 session 再次调用不会出错
2. **停止后发新消息** — 下一次 `POST /api/chat/{id}` 会自动重建 session，正常生成
3. **不要依赖超时停止** — 服务端没有自动停止机制，必须客户端显式调用
4. **工具执行中也可停止** — 即使 AI 正在执行 shell 命令/技能，stop 也会中断

---

## 断线恢复

### GET /api/chat/state/{session_id}

获取当前流式输出的快照，用于断线重连后恢复显示。

```
GET http://localhost:8765/api/chat/state/{session_id}
```

**有流式输出时**返回：

```json
{
  "message_id": "msg_966f9cca494b",
  "content": "当前时间是 2026年5月30日",
  "thinking": "",
  "role": "assistant",
  "timestamp": 1780150094.123
}
```

**无流式输出**时返回：

```json
{
  "message_id": null,
  "content": "",
  "thinking": "",
  "role": "assistant",
  "timestamp": 0
}
```

恢复流程：

1. 获取 `/api/chat/state/{id}` → 检查 `message_id` 是否非空
2. 如果非空，将 `content` 渲染到 UI，标记为"接收中"
3. 重新建立 SSE 连接 → 继续接收后续 chunk

---

## 会话管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/sessions` | 创建会话 `{"agent_id":"main_agent"}` |
| `GET` | `/api/sessions` | 列出所有会话（按 `last_active_time` 排序） |
| `GET` | `/api/sessions/{id}` | 获取会话详情 |
| `PATCH` | `/api/sessions/{id}` | 更新会话 `{"name":"新名称"}` |
| `DELETE` | `/api/sessions/{id}` | 删除会话及所有消息 |
| `GET` | `/api/sessions/{id}/messages` | 获取历史消息列表 |
| `DELETE` | `/api/sessions/{id}/messages` | 清空消息历史 |
| `POST` | `/api/sessions/{id}/unread/clear` | 清除未读计数 |
| `GET` | `/api/sessions/unread` | 获取所有会话未读计数 |

### 创建会话

```bash
curl -s -X POST http://localhost:8765/api/sessions \
  -H 'Content-Type: application/json' \
  -d '{"agent_id": "main_agent"}'
```

```json
{
  "session_id": "abc12345",
  "agent_id": "main_agent",
  "created_at": "...",
  "last_active_time": 1780150094
}
```

### 获取历史消息

```bash
curl http://localhost:8765/api/sessions/{session_id}/messages
```

```json
[
  {
    "role": "user",
    "content": "你好",
    "message_id": "msg_xxx"
  },
  {
    "role": "assistant",
    "content": "你好！有什么可以帮你的？",
    "message_id": "msg_yyy"
  }
]
```

---

## 完整代码示例

### Python 示例

```python
"""FastClaw SSE 客户端示例"""
import requests
import json
import threading
import time

BASE = "http://localhost:8765"


def main():
    # 1. 创建会话
    resp = requests.post(f"{BASE}/api/sessions",
                         json={"agent_id": "main_agent"})
    session = resp.json()
    session_id = session["session_id"]
    print(f"Session: {session_id}")

    # 2. 在后台线程建立 SSE 长连接
    events = []

    def sse_reader():
        with requests.get(
            f"{BASE}/api/chat/stream/{session_id}",
            stream=True,
            headers={"Accept": "text/event-stream"}
        ) as resp:
            event_type = None
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
                    events.append({"type": event_type, "data": data})

                    if event_type == "message.chunk":
                        print(data["delta"], end="", flush=True)
                    elif event_type == "message.end":
                        print("\n--- 回复结束 ---")
                    elif event_type == "error":
                        print(f"\n错误: {data['error']}")

    reader = threading.Thread(target=sse_reader, daemon=True)
    reader.start()
    time.sleep(0.5)  # 等 SSE 连接建立

    # 3. 发送消息
    resp = requests.post(
        f"{BASE}/api/chat/{session_id}",
        json={"text": "你好，请一句话介绍你自己"}
    )
    print(f"消息已发送: {resp.json()['message_id']}")

    # 4. 等回复完成
    time.sleep(10)
    print(f"\n共收到 {len(events)} 个 SSE 事件")


if __name__ == "__main__":
    main()
```

### JavaScript 示例

```javascript
const BASE = "http://localhost:8765";

async function chatExample() {
  // 1. 创建会话
  const sessionResp = await fetch(`${BASE}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_id: "main_agent" }),
  });
  const { session_id } = await sessionResp.json();

  // 2. 建立 SSE 连接
  const eventSource = new EventSource(
    `${BASE}/api/chat/stream/${session_id}`
  );

  eventSource.addEventListener("message.start", (e) => {
    console.log("[开始]", JSON.parse(e.data));
  });

  eventSource.addEventListener("message.chunk", (e) => {
    const { delta } = JSON.parse(e.data);
    process.stdout.write(delta);  // 流式输出
  });

  eventSource.addEventListener("message.tool_start", (e) => {
    const { tool_info } = JSON.parse(e.data);
    console.log(`\n[工具] ${tool_info}`);
  });

  eventSource.addEventListener("message.end", () => {
    console.log("\n[结束]");
  });

  eventSource.addEventListener("error", (e) => {
    if (e.data) {
      console.error("[错误]", JSON.parse(e.data));
    }
    eventSource.close();
  });

  eventSource.onerror = () => {
    console.error("SSE 连接断开");
  };

  // 3. 发送消息
  await fetch(`${BASE}/api/chat/${session_id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: "你好，请一句话介绍你自己" }),
  });
}

chatExample();
```

---

## 最佳实践

1. **先连 SSE，再发 POST** — 确保 SSE 连接在引擎产生事件之前就位，避免首 chunk 延迟
2. **复用 SSE 连接** — 同一会话的多轮对话使用同一条 SSE 连接，不要每条消息都重建（`message.end` 后连接不断开）
3. **用 `client_message_id` 去重** — 防止网络重试导致重复消息
4. **每个 chunk 做增量拼接** — `content += delta`，不要在每帧做完整重渲染
5. **`message.end` 触发后处理** — 停止累加、保存到历史、刷新 UI；对于移动端/后台 app，此时可以更新通知
6. **断线自动恢复** — 监听 `EventSource.onerror`，调用 `/api/chat/state/{id}` 取回未完成内容，然后重连 SSE
7. **心跳忽略** — SSE 注释行 `: heartbeat\n\n` 只在底层 `read()` 中出现，`EventSource` API 自动过滤；用 `requests.iter_lines()` 时跳过以 `:` 开头的行
8. **超时设置** — `POST /api/chat/{id}` 建议 30s 连接超时 + 3 分钟读取超时；SSE 连接无须设置超时，心跳机制会维持
