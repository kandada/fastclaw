# 飞书渠道配置与命令

## 概述

FastClaw 支持飞书作为消息渠道，可以通过飞书机器人与 AI 对话。除了 WebUI 外，还支持 CLI、飞书、Telegram、iMessage 等多个渠道。

## 飞书配置

### 1. 创建飞书应用

1. 访问 [飞书开放平台](https://open.feishu.cn/)
2. 创建一个企业自建应用
3. 获取 `app_id` 和 `app_secret`

### 2. 配置机器人

在飞书开放平台的应用配置中，启用机器人功能。

### 3. 权限管理

在 **权限管理** 中，至少需要添加以下权限：

| 权限名称 | 权限标识 | 说明 |
|---------|---------|------|
| 获取与发送单聊消息 | `im:message.p2p_msg:readonly` | 读取私聊消息 |
| 发送消息 | `im:message` | 发送消息 |
| 获取用户信息 | `im:chat.member:read` | 获取群成员信息 |

如果需要操作飞书文档，还需要添加文档相关权限。

### 3.1 文档操作权限配置

飞书文档操作需要配置两类权限：**应用权限** 和 **用户权限**。

#### 应用权限（用于 tenant_access_token）

在 **权限管理 → 应用权限** 中添加：

| 权限名称 | 权限标识 | 说明 |
|---------|---------|------|
| 获取云文档元数据 | `docx:document:readonly` | 读取文档信息 |
| 云文档 | `docx:document` | 创建/编辑文档 |
| 获取云空间元数据 | `drive:drive:readonly` | 读取云盘文件 |
| 云空间 | `drive:drive` | 云盘文件操作 |
| 知识库 | `wiki:wiki` | 知识库读写 |

#### 用户权限（用于 user_access_token）

某些操作（如搜索用户私有的 Wiki 知识库）需要用户授权。在 **权限管理 → 用户权限** 中添加：

| 权限名称 | 权限标识 | 说明 |
|---------|---------|------|
| 知识库 | `wiki:wiki` | 访问用户的 Wiki 知识库 |
| 知识库只读 | `wiki:wiki:readonly` | 只读访问 Wiki |

**重要**：用户权限需要用户在使用时额外授权。授权流程：
1. 调用 `get_auth_url` 获取授权链接
2. 用户扫码授权
3. 调用 `exchange_user_token` 交换授权码获取 user_access_token

### 4. 事件订阅

在 **事件订阅** 中，选择“长连接”，添加以下事件：

- `im.message.receive_v1` - 接收消息事件

### 5. 配置连接

编辑 `workspace/data/channels/feishu.json`：

```json
{
  "app_id": "cli_xxxxxxxxxxxxxxx",
  "app_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

## 启动飞书渠道

```bash
python main.py channel enable feishu
python main.py start
```

## 对话命令

在飞书、CLI、Telegram、iMessage 等非 WebUI 渠道中，可以使用以下命令管理会话：

| 命令 | 说明 |
|------|------|
| `/new` | 创建新会话 |
| `/clear` | 清空当前会话的聊天记录 |
| `/session <session_id>` | 切换到指定会话 |
| `/session_list` | 列出所有会话 ID |

### /new - 新建会话

```
用户: /new
助手: 已创建新会话，会话 ID：feishu_a1b2c3d4
```

创建新会话后，后续消息将在新会话中处理。

### /clear - 清空聊天记录

```
用户: /clear
助手: 已清空当前会话（feishu_a1b2c3d4）的聊天记录
```

这只会删除聊天消息，不会删除会话本身。

### /session - 切换会话

```
用户: /session feishu_a1b2c3d4
助手: 已切换到会话 feishu_a1b2c3d4
```

切换后，后续消息将在指定会话中处理。

### /session_list - 查看所有会话

```
用户: /session_list
助手: 当前所有会话:
  - feishu_a1b2c3d4 (agent: main_agent) <-- 当前
  - feishu_e5f6g7h8 (agent: main_agent)
  - cli_i9j0k1l2 (agent: main_agent)
```

## 会话 ID 规则

不同渠道的会话有不同前缀：

| 前缀 | 渠道 |
|------|------|
| `cli_` | 命令行界面 |
| `feishu_` | 飞书 |
| `telegram_` | Telegram |
| `imessage_` | iMessage |
| 无前缀 | WebUI |

## 注意事项

1. **渠道隔离**：不同渠道的会话相互独立，但可以通过 `/session` 命令互相切换
2. **会话持久化**：CLI 渠道的会话会保存到 `sessions.json`，重启后可继续
3. **消息转发**：WebUI 创建的会话不会出现在飞书，反之亦然
