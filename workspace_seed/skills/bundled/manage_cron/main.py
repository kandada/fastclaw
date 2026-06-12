async def execute(**kwargs) -> str:
    return """定时任务数据文件：workspace/data/cron/tasks.json（JSON 数组）

操作流程：
1. 先用 cat workspace/data/cron/tasks.json 读取现有任务
2. 用 Python 脚本安全合并：将新任务追加到现有数组，再写回文件
3. scheduler 每 60 秒自动从磁盘同步，新任务会在下一轮检查时生效

查看：cat workspace/data/cron/tasks.json
删除：读取后过滤掉对应条目再写回

创建任务的必填字段：
- id: 唯一标识（字母数字下划线）
- name: 任务名称
- schedule: 5段 cron 表达式（如 "0 9 * * *"），禁止全 *（"* * * * *"）
- description: 触发时发送的内容
- agent_id: "main_agent"
- session_id: 如用户未指定，使用当前会话的 session_id
- enabled: true

写入示例（使用 python3 安全合并）：
python3 -c "
import json
with open('workspace/data/cron/tasks.json') as f:
    tasks = json.load(f)
tasks.append({...新任务字段...})
with open('workspace/data/cron/tasks.json', 'w') as f:
    json.dump(tasks, f, ensure_ascii=False, indent=2)
"

注意：必须合并写入，严禁用 > 直接覆盖。这是 fastclaw 内置定时任务系统，不要使用 crontab -e。"""
