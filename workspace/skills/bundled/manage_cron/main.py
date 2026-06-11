async def execute(**kwargs) -> str:
    return """定时任务数据文件：workspace/data/cron/tasks.json（JSON 数组）

查看：cat workspace/data/cron/tasks.json
删除：从数组中移除对应条目

创建：用 run_shell 写入，每条任务字段：
id（唯一标识）、name、schedule（5段 cron，如 "0 9 * * *"）、description（触发内容）、agent_id（"main_agent"）、session_id、enabled（true）
如用户未指定绑定的会话，session_id 使用当前会话。先 cat 已有任务再合并写入，不要覆盖。

这是 fastclaw 内置定时任务系统，不要使用 crontab -e。"""
