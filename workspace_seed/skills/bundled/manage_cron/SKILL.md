## Description
Manage cron tasks — create, view, and delete scheduled tasks. Data file: workspace/data/cron/tasks.json (JSON array)

## Parameters
None. Calling this skill returns the instructions below; the model follows them using run_shell to read/write tasks.json.

## Example
1. View: run_shell("cat workspace/data/cron/tasks.json")
2. Create: first cat the existing tasks, merge the new task with python3 -c "...", then write back. NEVER use > to overwrite directly.
3. Delete: first cat the existing tasks, filter, then write back.

Task fields: id, name, schedule (5-field cron expression, never use all *), description, agent_id ("main_agent"), session_id (use the current session if not specified), enabled (true).

The scheduler automatically syncs new tasks from disk every 60 seconds. Do NOT use crontab -e.
