## Description
管理定时任务 — 创建/查看/删除定时任务。数据文件：workspace/data/cron/tasks.json（JSON 数组）

## Parameters
无。调用后返回操作说明，模型根据说明通过 run_shell 读写 tasks.json 完成任务管理。

## Example
1. 查看：run_shell("cat workspace/data/cron/tasks.json")
2. 创建：先 cat 读取现有任务，用 python3 -c "..." 合并新任务再写回，严禁直接用 > 覆盖
3. 删除：先 cat 读取，过滤后写回

任务字段：id、name、schedule（5段 cron，禁止全 *）、description、agent_id（"main_agent"）、session_id（未指定时用当前会话）、enabled（true）。

scheduler 每 60 秒自动从磁盘同步新任务。不要使用 crontab -e。
