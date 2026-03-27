# Workspace 目录结构

## 概述

`workspace/` 目录存储 FastClaw 的所有配置、数据和扩展文件。

## 目录结构

```
workspace/
├── settings.json          # 全局设置
├── agents/               # Agent 配置
│   └── main_agent.yaml
├── skills/               # 技能模块
│   ├── bundled/          # 内置技能
│   │   ├── current_time/
│   │   ├── feishu/
│   │   └── imessage/
│   └── user/             # 用户技能
│       └── _template/
└── data/                 # 数据目录
    ├── cron/             # 定时任务
    │   └── tasks.json
    └── sessions/         # 会话数据
        ├── session1/
        │   └── messages.jsonl
        └── session2/
            └── messages.jsonl
```

## 各目录说明

### settings.json

全局配置文件，包括默认 Agent 等设置。

### agents/

存放 Agent 配置文件（YAML 格式）。

### skills/

技能模块目录。

- `bundled/` - 内置技能，不可修改
- `user/` - 用户创建的技能，可自由修改

### data/

运行时数据目录。

#### cron/tasks.json

定时任务配置，格式：

```json
[
  {
    "id": "task_xxx",
    "name": "任务名",
    "schedule": "0 9 * * *",
    "description": "任务描述",
    "agent_id": "main_agent",
    "session_id": "default",
    "enabled": true
  }
]
```

#### sessions/

每个会话一个目录，存储消息历史。

格式为 JSONL（每行一个 JSON 对象）：

```
{"role": "user", "content": "你好"}
{"role": "assistant", "content": "你好！"}
```

## 备份建议

重要数据：
- `workspace/settings.json`
- `workspace/agents/`
- `workspace/data/`

建议定期备份这些目录。
