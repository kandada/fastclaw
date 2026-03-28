# FastClaw

一款python版的轻量但强大的龙虾

## 设计思想

FastClaw 基于**事件驱动的 Agent 编排**核心概念。主要设计原则：

- **图式 Agent**：使用有向图编排 Agent 行为，支持节点间的条件分支（如工具执行、回复生成）
- **事件流式输出**：实时流式输出 LLM 回复，提升用户体验
- **工具系统**：可扩展的工具框架，支持 Shell 命令、技能和自定义集成
- **会话管理**：持久化的对话历史，支持多会话
- **定时任务**：内置 Cron 风格的定时任务调度

## 快速开始

### 安装

```bash
git clone https://github.com/kandada/fastclaw.git
cd fastclaw
pip install -r requirements.txt
```

### 启动服务

```bash
python main.py start
# 持久化运行
nohup python main.py start > fastclaw.log 2>&1 &
```

### Agent设置
```bash
vim workspace/data/agents/main_agent/metadata.json 
# 或直接打开文件填写供应商和秘钥，当前仅支持openai网关的模型，包括deepseek等多数模型，推荐deepseek-chat
# 默认agent为 main_agent，如需切换，可在 workspace/data/settings.json 中修改
```

访问 http://localhost:8765
在settings页面中也可选取agent填入模型秘钥
只有填入模型秘钥，agent才能正常工作

### 命令行使用

```bash
# 交互式聊天
python main.py chat

# 新建会话
python main.py chat --new

# 查看状态
python main.py status
```

## 功能特性

- 🤖 **大模型驱动** - 基于 [FastMind](https://github.com/kandada/fastmind) 框架，支持流式输出。
- 🔧 **工具调用** - 执行 Shell 命令、技能等
- ⏰ **定时任务** - Cron 表达式调度任务
- 💬 **多渠道消息** - 飞书、iMessage 集成
- 🎨 **可扩展** - 易于添加自定义技能和 Agent

## 开源许可

GPL-3.0

## 致谢

受 [OpenClaw](https://github.com/openclaw/openclaw) 启发。感谢开源社区。

---

fastclaw很强大，用处还坏全看使用者怎么用，一切责任由使用者自己承担

---

作者：[xiefujin](https://github.com/kandada) email: 490021684@qq.com，welcome to contact me.
