# FastClaw

a python-based light but strong lobster

## Design Philosophy

FastClaw is built on the core concept of **event-driven agent orchestration**. Key design principles:

- **Graph-based Agent**: Uses a directed graph to orchestrate agent behavior, supporting conditional branching between nodes (e.g., tool execution, response generation)
- **Event Streaming**: Real-time streaming output of LLM responses for better user experience
- **Tool System**: Extensible tool framework supporting Shell commands, skills, and custom integrations
- **Session Management**: Persistent conversation history with multi-session support
- **Cron Scheduling**: Built-in cron-style task scheduling for automated workflows

## Quick Start

### Installation

```bash
git clone https://github.com/kandada/fastclaw.git
cd fastclaw
pip install -r requirements.txt
```

### Start Server

```bash
python main.py start
# or want it remaining in background:
nohup python main.py start > fastclaw.log 2>&1 &
```

### Agent Configuration

```bash
vim workspace/data/agents/main_agent/metadata.json
# Edit the file to configure your LLM provider and API key
# Currently supports OpenAI gateway models (DeepSeek, OpenAI, etc.), recommended: deepseek-chat
# Default agent is main_agent. To switch, modify workspace/data/settings.json
```

Access at http://localhost:8765

### CLI Usage

```bash
# Interactive chat
python main.py chat

# New session
python main.py chat --new

# Check status
python main.py status
```

## Features

- 🤖 **LLM-powered** - Built on FastMind framework with streaming support
- 🔧 **Tool Calling** - Execute Shell commands, skills, and more
- ⏰ **Cron Jobs** - Schedule tasks with cron expressions
- 💬 **Multi-channel** - Feishu, iMessage integrations
- 🎨 **Extensible** - Easy to add custom skills and agents

## License

GPL-3.0

## Acknowledgments

Inspired by [OpenClaw](https://github.com/openclaw/openclaw). Special thanks to the open source community.

---
FastClaw is powerful, but its use depends entirely on the user - all responsibility lies with the user yourself.

---

Author: [xiefujin](https://github.com/kandada)
