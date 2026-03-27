# 命令行使用

## 基本命令

```bash
python3 main.py <command>
```

## 命令列表

### 服务管理

```bash
python3 main.py start          # 启动 web 服务
python3 main.py status        # 查看运行状态
python3 main.py help          # 显示帮助信息
```

### 交互式聊天

```bash
python3 main.py chat                    # 使用默认会话聊天
python3 main.py chat --new              # 创建新会话聊天
python3 main.py chat --session-id <id>  # 继续指定会话
```

### 会话管理

```bash
python3 main.py session list          # 列出所有会话
python3 main.py session history <id>   # 查看会话历史
python3 main.py session clear <id>     # 清空会话消息
python3 main.py session export <id>   # 导出会话
```

### 定时任务

```bash
python3 main.py cron list            # 列出所有定时任务
python3 main.py cron add             # 添加定时任务（交互式）
python3 main.py cron del <name>      # 删除定时任务
python3 main.py cron run <name>      # 手动触发任务
```

### 技能管理

```bash
python3 main.py skill list           # 列出所有技能
python3 main.py skill info <name>    # 查看技能详情
python3 main.py skill test <name>    # 测试技能
```

### Agent 管理

```bash
python3 main.py agent list           # 列出所有 Agent
python3 main.py agent info <name>    # 查看 Agent 配置
```

## 使用别名

如果不使用别名，需要加上 PYTHONPATH：

```bash
PYTHONPATH="${PWD}/vendor:$PYTHONPATH" python3 main.py status
```

建议设置别名以简化操作，详见[安装指南](installation.md)。

## 示例

```bash
# 启动服务
python main.py start

# 新窗口中查看状态
python main.py status

# 开始聊天
python main.py chat --new

# 继续指定会话
python main.py chat --session-id 08fc753b

# 查看会话列表
python main.py session list

# 查看定时任务
python main.py cron list
```
