# FastClaw

一款 python 版的轻量但强大的龙虾，是灵活可靠的通用 AI Agent 框架, 尤其擅长处理数据科学领域的任务。

## PyPI 安装（推荐）

```bash
# 安装
pip install fastclaw-ai

# 运行
fastclaw start

# 持久化运行（推荐用于服务器）
nohup fastclaw start > /tmp/fastclaw.log 2>&1 &
```

### 配置 Agent

启动后访问 http://localhost:8765 ，点右上角 Settings 进入页面设置 main_agent，推荐使用 deepseek-chat。

或编辑配置文件：
```bash
vim ~/.fastclaw/workspace/data/agents/main_agent/metadata.json
```

### 命令行使用

```bash
# 交互式聊天
fastclaw chat

# 新建会话
fastclaw chat --new

# 查看状态
fastclaw status
```

---

## Git 克隆安装

```bash
git clone https://github.com/kandada/fastclaw.git
cd fastclaw
pip install -r requirements.txt
```

```bash
# 运行
python main.py start

# 持久化运行
nohup python main.py start > fastclaw.log 2>&1 &
```

### 配置 Agent

启动后访问 http://localhost:8765 ，点右上角 Settings 进入页面设置 main_agent，推荐使用 deepseek-chat。

或编辑配置文件：
```bash
vim workspace/data/agents/main_agent/metadata.json
```

### 命令行使用

```bash
# 交互式聊天
python main.py chat

# 新建会话
python main.py chat --new

# 查看状态
python main.py status
```

---

## 设计思想

FastClaw 基于**事件驱动的 Agent 编排**核心概念。主要设计原则：

- **图式 Agent**：使用有向图编排 Agent 行为，支持节点间的条件分支（如工具执行、回复生成）
- **事件流式输出**：实时流式输出 LLM 回复，提升用户体验
- **工具系统**：可扩展的工具框架，支持 Shell 命令、技能和自定义集成
- **会话管理**：持久化的对话历史，支持多会话
- **定时任务**：内置 Cron 风格的定时任务调度

## 功能特性

- 🤖 **大模型驱动** - 基于 [FastMind](https://github.com/kandada/fastmind) 框架，支持流式输出
- 🔧 **工具调用** - 执行 Shell 命令、技能等
- ⏰ **定时任务** - Cron 表达式调度任务
- 💬 **多渠道消息** - 飞书、iMessage 集成
- 🎨 **可扩展** - 易于添加自定义技能和 Agent
- 🐍 **Python 生态** - 无缝调用 numpy、pandas 等专业库，让 AI 像人类一样熟练使用 Python 生态的各种工具

## 更新日志

### v1.1.16 (2026-06-26)
- 🔧 优化：将 `ripgrep` 改为可选依赖，避免无 MSVC 的 Windows 环境编译失败
- 🔧 优化：新增 Python 3.13 / 3.14 支持

### v1.1.15 (2026-06-12)

### v1.1.14 (2026-06-12)

### v1.1.13 (2026-06-12)

### v1.1.12 (2026-06-11)
- 🐛 修复：WebUI 的一些 bug 和定时任务的一些 bug

### v1.1.11 (2026-06-02)

### v1.1.10 (2026-05-31)

### v1.1.9 (2026-05-31)

### v1.1.8 (2026-05-25)
- ✨ 特性：WebUI 的 Agent 编辑页面新增 LLM Gateway 选择器（OpenAI / Anthropic）
- ✨ 特性：工作空间为空时自动从 GitHub 拉取默认 Agent 配置
- ✨ 特性：settings.json 缺失时自动生成默认配置
- 🔧 优化：默认 Unload Threshold 从 80k 提升至 156k

### v1.1.7 (2026-05-21)
- 🐛 修复：上下文卸载仅影响 LLM 输入，messages.jsonl 始终保留完整历史
- 🐛 修复：消息时间戳不再被每次保存时覆盖
- 🐛 修复：CancelledError 不再触发重复回答生成
- 🧪 测试：新增上下文卸载、滑动窗口、时间戳保留等测试

## 开源许可

GPL-3.0

版权所有 © 2024-2026 xiefujin。保留所有权利。

## 官网

[https://www.fastclaw.world/](https://www.fastclaw.world/) | [https://fastclaw-ai.com/](https://fastclaw-ai.com/)

## 致谢

受 [OpenClaw](https://github.com/openclaw/openclaw) 启发。感谢开源社区。

---

fastclaw 很强大，用处好坏全看使用者怎么用，一切责任由使用者自己承担

---

作者：[xiefujin](https://github.com/kandada) email: 490021684@qq.com，welcome to contact me.
