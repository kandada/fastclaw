# 技能开发

## 概述

技能（Skills）是 FastClaw 的可扩展功能模块，允许自定义工具供 Agent 调用。

## 技能目录

```
workspace/skills/
├── bundled/          # 内置技能
│   ├── current_time/ # 获取当前时间
│   ├── feishu/       # 飞书消息
│   └── imessage/     # iMessage
└── user/             # 用户自定义技能
    └── _template/    # 模板
```

## 技能结构

每个技能是一个目录，包含：

```
skill_name/
├── __init__.py      # 技能入口
└── skill.json       # 技能配置
```

## 开发示例

### 1. 创建技能目录

```bash
mkdir -p workspace/skills/user/my_skill
```

### 2. 创建 skill.json

```json
{
  "name": "my_skill",
  "description": "我的自定义技能",
  "parameters": {
    "arg1": "参数1说明",
    "arg2": "参数2说明"
  }
}
```

### 3. 创建 __init__.py

```python
"""我的自定义技能"""

def execute(param1, param2):
    """执行技能"""
    # 在这里实现技能逻辑
    result = f"处理 {param1} 和 {param2}"
    return result

# 如果需要特定的调用格式
def run(param1, param2):
    return execute(param1, param2)
```

## 调用技能

技能被 Agent 通过 `run_skills` 工具调用：

```json
{
  "function": {
    "name": "run_skills",
    "arguments": "{\"skill_name\": \"my_skill\", \"params\": {\"param1\": \"value1\"}}"
  }
}
```

## 内置技能

### current_time

获取当前日期和时间。

### feishu

发送飞书消息或获取消息。

参数：
- `action`: "send" | "receive"
- `message`: 消息内容（send 时使用）
- `session_id`: 飞书用户 ID（send 时使用）

### imessage

通过 AppleScript 发送 iMessage（仅 macOS）。

参数：
- `message`: 消息内容
- `receiver`: 接收人

## 测试技能

```bash
python main.py skill test <skill_name>
```

## 技能列表

```bash
python main.py skill list
```
