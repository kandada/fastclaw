# PyPI 安装指南

本文档介绍如何通过 PyPI 安装 FastClaw，以及安装后的使用方法。

## 环境要求

- Python 3.10 或更高版本
- pip 包管理器

## 安装方式

### 方式一：直接安装（推荐）

```bash
pip install fastclaw-ai
```

### 方式二：安装特定版本

```bash
pip install fastclaw-ai==1.1.0
```

### 方式三：升级版本

```bash
pip install --upgrade fastclaw-ai
```

## 快速开始

安装完成后，直接使用 `fastclaw` 命令：

```bash
# 启动服务
fastclaw start

# 查看状态
fastclaw status

# 交互式聊天
fastclaw chat
```

## 启动参数

### 启动服务

```bash
fastclaw start [选项]
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--host` | 服务监听地址 | 0.0.0.0 |
| `--port` | 服务监听端口 | 8765 |

示例：

```bash
# 默认端口启动
fastclaw start

# 指定端口启动
fastclaw start --port 8080

# 指定地址启动
fastclaw start --host 127.0.0.1 --port 9000
```

### 交互式聊天

```bash
fastclaw chat [选项]
```

| 选项 | 说明 |
|------|------|
| `--new` | 创建新会话 |
| `--session-id <id>` | 继续指定会话 |
| `--host` | 服务地址 |
| `--port` | 服务端口 |

示例：

```bash
# 新建聊天会话
fastclaw chat --new

# 继续指定会话
fastclaw chat --session-id abc123

# 指定端口
fastclaw chat --port 8080
```

## 停止服务

### 方式一：Ctrl+C

在运行 `fastclaw start` 的终端窗口中，按 `Ctrl+C` 发送中断信号，服务会优雅停止。

### 方式二：kill 进程

```bash
# 查找进程
ps aux | grep fastclaw

# 或使用 lsof 查找占用端口的进程
lsof -i :8765

# 终止进程
kill <PID>
```

### 方式三：删除 PID 文件

如果服务启动时创建了 PID 文件：

```bash
# 查看 PID 文件位置（默认 /tmp/fastclaw.pid）
cat /tmp/fastclaw.pid

# 使用 PID 终止
kill $(cat /tmp/fastclaw.pid)

# 删除 PID 文件
rm /tmp/fastclaw.pid
```

### 方式四：强制终止

```bash
# 强制终止所有 fastclaw 进程
pkill -f "fastclaw start"

# 或指定端口
pkill -f ":8765"
```

## 持久化运行

### nohup（推荐）

使用 nohup 让 FastClaw 在后台持续运行，关闭终端后不影响：

```bash
nohup fastclaw start > /tmp/fastclaw.log 2>&1 &
```

参数说明：
- `nohup ... &` - 后台运行，关闭终端不受影响
- `> /tmp/fastclaw.log` - 输出日志到文件
- `2>&1` - 错误输出重定向到标准输出

查看日志：
```bash
tail -f /tmp/fastclaw.log
```

停止持久化运行的服务：
```bash
pkill -f "fastclaw start"
```

## 数据目录

### 工作空间

安装后，FastClaw 的工作空间位于用户家目录：

| 系统 | 路径 |
|------|------|
| macOS / Linux | `~/.fastclaw/workspace` |
| Windows | `%USERPROFILE%\.fastclaw\workspace` |

### 目录结构

```
~/.fastclaw/workspace/
├── data/
│   ├── agents/          # Agent 配置
│   ├── sessions/        # 会话数据
│   ├── channels/        # 渠道配置
│   └── settings.json    # 全局设置
└── skills/             # 技能目录
    ├── bundled/         # 内置技能
    └── user/            # 用户技能
```

### 路径优先级

FastClaw 会按照以下优先级确定工作空间路径：

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | `FASTCLAW_WORKSPACE` 环境变量 | 最高优先级，设置后优先使用 |
| 2 | `fastclaw/` 包自身目录下的 `workspace/` | 适用于 GitHub 开源模式 |
| 3 | 项目根目录的 `workspace/` | 仅当存在且为目录时使用（开发模式） |
| 4 | `~/.fastclaw/workspace` | 默认路径（用户目录模式） |

**说明**：
- **环境变量**：适合需要完全自定义路径的场景
- **开源模式**：`fastclaw/` 包目录下有 `workspace/` 时使用，适合 GitHub 下载后直接使用的场景
- **开发模式**：适合从 GitHub 克隆源码后直接运行的情况
- **用户目录模式**：通过 PyPI 安装后的默认行为，数据存储在家目录下

**用户目录模式各系统路径**：

| 系统 | 路径 |
|------|------|
| macOS | `/Users/<username>/.fastclaw/workspace` |
| Linux | `/home/<username>/.fastclaw/workspace` |
| Windows | `C:\Users\<username>\.fastclaw\workspace` |

### 自定义工作空间

通过环境变量指定工作空间位置：

```bash
# Linux / macOS
export FASTCLAW_WORKSPACE=/path/to/your/workspace
fastclaw start

# Windows (CMD)
set FASTCLAW_WORKSPACE=C:\path\to\workspace
fastclaw start

# Windows (PowerShell)
$env:FASTCLAW_WORKSPACE="C:\path\to\workspace"
fastclaw start
```

## 配置 Agent

首次使用前，需要配置 LLM Agent：

1. 编辑 `~/.fastclaw/workspace/data/settings.json` 或通过 WebUI 配置
2. 配置示例：

```json
{
  "default_agent_id": "main_agent",
  "run_shell_timeout": 60,
  "run_skills_timeout": 60
}
```

3. 在 `~/.fastclaw/workspace/data/agents/main_agent/` 目录下创建 `metadata.json`：

```json
{
  "name": "main_agent",
  "llm": {
    "gateway": "openai",
    "provider": "deepseek",
    "model": "deepseek-chat",
    "api_key": "your-api-key",
    "base_url": "https://api.deepseek.com/v1",
    "multimodal": false
  },
  "context": {
    "max_tokens": 80000,
    "unload_threshold_tokens": 80000
  }
}
```

## 访问服务

启动后，访问以下地址：

| 服务 | 地址 |
|------|------|
| WebUI | http://localhost:8765 |
| API 端点 | http://localhost:8765/api/chat/{session_id} |
| WebSocket | ws://localhost:8765/ws |

## 常用命令

### 查看帮助

```bash
fastclaw help
```

### 会话管理

```bash
# 列出所有会话
fastclaw session list

# 查看会话历史
fastclaw session history <session_id>

# 清空会话消息
fastclaw session clear <session_id>

# 导出会话
fastclaw session export <session_id>
```

### Cron 任务

```bash
# 列出所有 Cron 任务
fastclaw cron list

# 触发任务（通过 API）
fastclaw cron run <task_name>
```

### 技能管理

```bash
# 列出所有技能
fastclaw skill list

# 查看技能详情
fastclaw skill info <skill_name>

# 测试技能
fastclaw skill test <skill_name>
```

### Agent 管理

```bash
# 列出所有 Agent
fastclaw agent list

# 查看 Agent 配置
fastclaw agent info <name>

# 添加新 Agent（交互式）
fastclaw agent add
```

## 卸载

```bash
pip uninstall fastclaw
```

卸载后，工作空间 `~/.fastclaw/` 不会被删除，如需清理请手动删除。

## 常见问题

### 1. 启动报错 "No module named 'fastclaw'"

确保通过 pip 安装：

```bash
pip install fastclaw-ai
```

### 2. 提示找不到 Agent 配置

检查工作空间中是否存在 Agent 配置：

```bash
ls ~/.fastclaw/workspace/data/agents/
```

### 3. 端口被占用

使用 `--port` 指定其他端口：

```bash
fastclaw start --port 8766
```

### 4. 需要使用自定义工作空间

```bash
export FASTCLAW_WORKSPACE=/path/to/workspace
fastclaw start
```

## 从源码迁移到 PyPI

如果之前从 GitHub 克隆源码使用，现在想切换到 PyPI 版本：

1. 卸载旧版本（如果在 editable 模式安装）：

```bash
pip uninstall fastclaw-ai
```

2. 安装 PyPI 版本：

```bash
pip install fastclaw-ai
```

3. 迁移工作空间数据（可选）：

```bash
# 将旧的工作空间内容复制到新位置
cp -r /path/to/old/workspace ~/.fastclaw/workspace
```

## 相关链接

- [GitHub 仓库](https://github.com/kandada/fastclaw)
- [源码安装指南](installation.md)
- [快速开始](quick-start.md)
- [WebUI 使用](webui.md)
- [CLI 详细用法](cli.md)
