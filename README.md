# FastClaw

A lightweight but powerful AI Agent framework in Python.

## PyPI Installation (Recommended)

```bash
# Install
pip install fastclaw-ai

# Run
fastclaw start

# Persistent running (recommended for server)
nohup fastclaw start > /tmp/fastclaw.log 2>&1 &
```

### Configure Agent

After starting, visit http://localhost:8765 , click Settings in the top right corner to configure main_agent, recommended: deepseek-chat.

Or edit the config file:
```bash
vim ~/.fastclaw/workspace/data/agents/main_agent/metadata.json
```

### CLI Usage

```bash
# Interactive chat
fastclaw chat

# New session
fastclaw chat --new

# Check status
fastclaw status
```

---

## Git Clone

```bash
git clone https://github.com/kandada/fastclaw.git
cd fastclaw
pip install -r requirements.txt
```

```bash
# Run
python main.py start

# Persistent running
nohup python main.py start > fastclaw.log 2>&1 &
```

### Configure Agent

After starting, visit http://localhost:8765 , click Settings in the top right corner to configure main_agent, recommended: deepseek-chat.

Or edit the config file:
```bash
vim workspace/data/agents/main_agent/metadata.json
```

### CLI Usage

```bash
# Interactive chat
python main.py chat

# New session
python main.py chat --new

# Check status
python main.py status
```

---

## Design Philosophy

FastClaw is built on the core concept of **event-driven agent orchestration**. Key design principles:

- **Graph-based Agent**: Uses a directed graph to orchestrate agent behavior, supporting conditional branching between nodes (e.g., tool execution, response generation)
- **Event Streaming**: Real-time streaming output of LLM responses for better user experience
- **Tool System**: Extensible tool framework supporting Shell commands, skills, and custom integrations
- **Session Management**: Persistent conversation history with multi-session support
- **Cron Scheduling**: Built-in cron-style task scheduling for automated workflows

## Features

- 🤖 **LLM-powered** - Built on [FastMind](https://github.com/kandada/fastmind) framework with streaming support
- 🔧 **Tool Calling** - Execute Shell commands, skills, and more
- ⏰ **Cron Jobs** - Schedule tasks with cron expressions
- 💬 **Multi-channel** - Feishu, iMessage integrations
- 🎨 **Extensible** - Easy to add custom skills and agents
- 🐍 **Python Ecosystem** - Seamlessly call professional libraries like numpy and pandas, enabling AI to use Python ecosystem tools as skillfully as humans

## Changelog

### v1.1.19 (2026-06-29)
- 🐛 Fix: Resolved `SyntaxError` on Python 3.10/3.11 caused by backslash (`\`) inside f-string `{}` expressions (a Python 3.12+ syntax)
- 🔧 Improvement: Added version compatibility comments at f-string usage sites to prevent future regressions

### v1.1.18 (2026-06-27)
- 🔧 Improvement: Added copyright and GPLv3 license headers to all source files

### v1.1.17 (2026-06-27)
- 🐛 Fix: Resolved `UnicodeDecodeError` on Windows Chinese systems by adding `encoding="utf-8"` to all `read_text()` / `write_text()` calls, fixing the crash on second startup
- 🐛 Fix: WebUI agent edit/create buttons now show error messages on failure instead of silently doing nothing
- 🐛 Fix: Removed 3 extra `</div>` tags from WebUI HTML that could cause DOM parsing issues
- 🔧 Improvement: Startup messages now show `http://localhost:{port}` alongside `http://0.0.0.0:{port}` for easier access on Windows
- 🔧 Improvement: Added diagnostic logging to silent `except` blocks in router.py for easier debugging

### v1.1.16 (2026-06-26)
- 🔧 Improvement: Made `ripgrep` an optional dependency to avoid compilation issues on Windows without MSVC
- 🔧 Improvement: Added Python 3.13 / 3.14 support

### v1.1.15 (2026-06-12)

### v1.1.14 (2026-06-12)

### v1.1.13 (2026-06-12)

### v1.1.12 (2026-06-11)
- 🐛 Fix: WebUI bugs and cron scheduler bugs

### v1.1.11 (2026-06-02)

### v1.1.10 (2026-05-31)

### v1.1.9 (2026-05-31)

### v1.1.8 (2026-05-25)
- ✨ Feature: LLM Gateway selector (OpenAI / Anthropic) in WebUI agent settings
- ✨ Feature: Auto-bootstrap default agents from GitHub when workspace is empty
- ✨ Feature: Auto-generate settings.json with defaults when missing
- 🔧 Improvement: Increased default Unload Threshold from 80k to 156k

### v1.1.7 (2026-05-21)
- 🐛 Fix: Context unloading now only affects LLM input, messages.jsonl always keeps full history
- 🐛 Fix: Message timestamps are no longer overwritten on every save
- 🐛 Fix: CancelledError no longer triggers duplicate response generation
- 🧪 Test: Added context unloading, sliding window, and timestamp preservation tests

## License

GPL-3.0

Copyright (c) 2024-2026 xiefujin. All rights reserved.

## Official Website

[https://www.fastclaw.world/](https://www.fastclaw.world/) | [https://fastclaw-ai.com/](https://fastclaw-ai.com/)

## Acknowledgments

Inspired by [OpenClaw](https://github.com/openclaw/openclaw). Special thanks to the open source community.

---

FastClaw is powerful, but its use depends entirely on the user - all responsibility lies with the user yourself.

---

Author：[xiefujin](https://github.com/kandada) email: 490021684@qq.com，welcome to contact me.
