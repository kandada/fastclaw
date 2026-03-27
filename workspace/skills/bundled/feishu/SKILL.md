## Description
发送消息到飞书或获取飞书消息

## Parameters
- action: 操作类型 ("send" | "receive")
- message: 消息内容（send时使用）
- session_id: 飞书用户ID（send时使用）

## Example
发送消息: run_skills("feishu", {"action": "send", "message": "Hello", "session_id": "ou_xxx"})
