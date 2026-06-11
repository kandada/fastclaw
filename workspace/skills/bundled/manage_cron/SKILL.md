## Description
管理定时任务 — 创建/查看/删除定时任务。数据文件：workspace/data/cron/tasks.json（JSON 数组）

## Parameters
无。调用后返回操作说明，模型根据说明通过 run_shell 读写 tasks.json 完成任务管理。

## Example
查看：run_shell("cat workspace/data/cron/tasks.json")
创建/删除：用 run_shell 直接编辑 tasks.json，任务字段：id、name、schedule（5段 cron）、description、agent_id（"main_agent"）、session_id、enabled（true）。先 cat 再合并，不要覆盖已有任务。未指定会话时使用当前会话。
