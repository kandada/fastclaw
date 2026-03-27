# 快速开始

## 环境要求

- Python 3.12+
- macOS / Linux / Windows

## 快速启动

```bash
# 克隆项目
git clone <repository-url>
cd fastclaw_local

# 安装依赖
pip install -r requirements.txt

# 启动服务
python main.py start
```

## 访问服务

启动后访问：http://localhost:8765

## 基本使用

### 1. WebUI 交互

1. 打开浏览器访问 http://localhost:8765
2. 选择或创建会话
3. 开始对话

### 2. 命令行交互

```bash
# 启动交互式聊天
python main.py chat

# 新建会话聊天
python main.py chat --new

# 继续指定会话
python main.py chat --session-id <session_id>
```

### 3. 查看状态

```bash
# 查看服务状态
python main.py status
```

## 下一步

- [命令行详细使用](cli.md)
- [WebUI 详细功能](webui.md)
- [技能开发](skills.md)
