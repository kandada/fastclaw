# 定时任务

## 概述

定时任务（Cron）允许在指定时间自动触发 Agent 执行任务。

## Cron 表达式

标准 5 段式 Cron 格式：

```
┌───────────── 分钟 (0-59)
│ ┌───────────── 小时 (0-23)
│ │ ┌───────────── 日期 (1-31)
│ │ │ ┌───────────── 月份 (1-12)
│ │ │ │ ┌───────────── 星期 (0-6，0 是周日)
│ │ │ │ │
* * * * *
```

## 示例

| 表达式 | 说明 |
|--------|------|
| `0 9 * * *` | 每天 9:00 |
| `30 8 * * 1-5` | 工作日 8:30 |
| `0 */2 * * *` | 每 2 小时 |
| `15 14 * * *` | 每天 14:15 |

## 管理任务

### WebUI

1. 打开 Cron 页面
2. 点击 **Add** 创建新任务
3. 填写任务信息
4. 点击 **Trigger** 手动触发

### CLI

```bash
# 列出所有任务
python main.py cron list

# 手动触发
python main.py cron run <name>
```

### API

```bash
# 创建任务
curl -X POST http://localhost:8765/api/crons \
  -H "Content-Type: application/json" \
  -d '{
    "name": "每天早安",
    "schedule": "0 9 * * *",
    "description": "给我一个问候",
    "agent_id": "main_agent",
    "session_id": "default",
    "enabled": true
  }'

# 触发任务
curl -X POST http://localhost:8765/api/crons/trigger \
  -H "Content-Type: application/json" \
  -d '{"task_id": "task_xxx"}'

# 删除任务
curl -X DELETE http://localhost:8765/api/crons/<task_id>
```

## 任务字段

| 字段 | 说明 |
|------|------|
| name | 任务名称 |
| schedule | Cron 表达式 |
| description | 任务描述（将作为用户消息发送给 Agent） |
| agent_id | 使用的 Agent ID |
| session_id | 目标会话 ID |
| enabled | 是否启用 |

## 数据存储

任务配置存储在：

```
workspace/data/cron/tasks.json
```
