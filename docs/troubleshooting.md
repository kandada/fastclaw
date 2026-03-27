# 故障排除

## 常见问题

### 1. 服务无法启动

**症状**：执行 `python main.py start` 报错

**可能原因**：
- 端口 8765 被占用
- Python 版本不对

**解决方法**：
```bash
# 检查端口占用
lsof -i :8765

# 使用其他端口
python main.py start --port 8766
```

### 2. 重复启动

**症状**：`FastClaw is already running!`

**解决方法**：
```bash
# 方法1：杀掉旧进程
kill <PID>

# 方法2：删除 PID 文件
rm /tmp/fastclaw.pid
```

### 3. API 调用失败

**症状**：返回错误或超时

**可能原因**：
- 服务未启动
- 网络问题
- API 密钥无效

**解决方法**：
```bash
# 检查服务状态
python main.py status

# 检查 API 配置
cat workspace/agents/main_agent.yaml
```

### 4. 技能不工作

**症状**：Agent 无法调用技能

**可能原因**：
- 技能目录结构不对
- 技能代码有错误

**解决方法**：
```bash
# 检查技能列表
python main.py skill list

# 检查技能目录
ls -la workspace/skills/
```

### 5. 会话丢失

**症状**：之前创建的会话不见了

**可能原因**：
- 数据文件损坏
- 使用了错误的 session_id

**解决方法**：
```bash
# 列出所有会话
python main.py session list
```

### 6. 内存占用高

**症状**：运行一段时间后内存占用大

**可能原因**：
- 多个服务实例同时运行
- 连接未正确关闭

**解决方法**：
```bash
# 检查 Python 进程
ps aux | grep python

# 重启服务
kill <PID>
python main.py start
```

## 日志

服务日志默认输出到 stdout。

如需持久化：

```bash
nohup python main.py start > fastclaw.log 2>&1 &
tail -f fastclaw.log
```

## 性能优化

1. **使用别名** - 减少 PYTHONPATH 设置开销
2. **检查进程** - 确保没有重复进程
3. **限制会话** - 定期清理不需要的会话

## 获取帮助

```bash
python main.py help
```

## 报告问题

如遇到无法解决的问题，请提供：

1. 服务日志
2. 复现步骤
3. 环境信息（Python 版本、操作系统）
