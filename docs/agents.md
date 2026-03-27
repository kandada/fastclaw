# Agent 配置

## 概述

Agent 是 FastClaw 的智能体核心，负责理解用户输入并生成回复。

## Agent 目录

```
workspace/agents/
└── main_agent.yaml   # 主 Agent 配置
```

## 配置结构

```yaml
name: main_agent
description: FastClaw 主智能体
llm:
  gateway: openai
  provider: deepseek
  model: deepseek-chat
  api_key: your-api-key
  base_url: https://api.deepseek.com/v1
  multimodal: false
context:
  max_tokens: 80000
  unload_threshold_tokens: 80000
extra_workspaces: []
```

## 配置项说明

### 基本信息

| 字段 | 说明 |
|------|------|
| name | Agent 名称 |
| description | Agent 描述 |

### LLM 配置

| 字段 | 说明 |
|------|------|
| gateway | 网关类型（openai） |
| provider | 模型提供商（deepseek/openai 等） |
| model | 模型名称 |
| api_key | API 密钥 |
| base_url | API 基础 URL |
| multimodal | 是否支持多模态 |

### Context 配置

| 字段 | 说明 |
|------|------|
| max_tokens | 最大 token 数 |
| unload_threshold_tokens | 卸载阈值 |

## 管理命令

```bash
# 列出所有 Agent
python main.py agent list

# 查看 Agent 配置
python main.py agent info <name>
```

## 切换默认 Agent

在 WebUI 的 Settings 页面修改 `default_agent_id`。
