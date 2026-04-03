## Description
飞书技能 - 支持发送消息和操作飞书云文档（创建、读取、编辑、分享等）

## Parameters
- action: 操作类型（必填）
  - send: 发送消息
  - create_doc: 创建云文档
  - get_doc: 获取文档信息
  - read_doc: 读取文档内容
  - append_doc: 追加文档内容
  - update_doc: 更新文档块内容
  - list_files: 列出云盘文件
  - create_folder: 创建文件夹
  - share_doc: 分享文档
  - search_wiki: 搜索知识库（需要用户授权）
  - get_auth_url: 获取OAuth授权URL
  - exchange_user_token: 交换授权码获取用户Token
  - refresh_user_token: 刷新用户Token
  - check_user_token: 检查用户Token状态

### send 参数
- message: 消息内容（必填）
- session_id: 飞书用户open_id（必填）

### create_doc 参数
- title: 文档标题（选填，默认"Untitled Document"）
- folder_token: 父文件夹token（选填）

### get_doc 参数
- document_id: 文档token（必填）

### read_doc 参数
- document_id: 文档token（必填）

### append_doc 参数
- document_id: 文档token（必填）
- block_id: 父块ID（选填，默认追加到文档根节点）
- content: 内容（必填）
- block_type: 块类型（选填，默认2=文本块）

### update_doc 参数
- document_id: 文档token（必填）
- block_id: 块ID（必填）
- content: 新内容（必填）

### list_files 参数
- folder_token: 文件夹token（选填，不填则列出根目录）
- page_size: 每页数量（选填，默认50）

### create_folder 参数
- name: 文件夹名称（必填）
- folder_token: 父文件夹token（选填）

### share_doc 参数
- document_id: 文档token（必填）
- member_id: 成员ID（必填）
- member_type: 成员类型（选填，默认"openid"）
- share_type: 权限类型（选填，默认"edit"，可设为"full_access"）

### search_wiki 参数
- query: 搜索关键词（必填）
- count: 返回数量（选填，默认10）
- 注意：需要先通过 get_auth_url 和 exchange_user_token 完成用户授权

### exchange_user_token 参数
- code: 授权码（必填，授权后从URL参数获取）

## Example
发送消息: run_skills("feishu", {"action": "send", "message": "Hello", "session_id": "ou_xxx"})

创建文档: run_skills("feishu", {"action": "create_doc", "title": "我的文档"})

获取文档: run_skills("feishu", {"action": "get_doc", "document_id": "xxx"})

读取文档: run_skills("feishu", {"action": "read_doc", "document_id": "xxx"})

追加内容: run_skills("feishu", {"action": "append_doc", "document_id": "xxx", "content": "新段落内容"})

更新块内容: run_skills("feishu", {"action": "update_doc", "document_id": "xxx", "block_id": "yyy", "content": "更新的内容"})

列出文件: run_skills("feishu", {"action": "list_files"})

创建文件夹: run_skills("feishu", {"action": "create_folder", "name": "新文件夹"})

分享文档: run_skills("feishu", {"action": "share_doc", "document_id": "xxx", "member_id": "ou_xxx", "share_type": "edit"})

搜索知识库（需先授权）:
1. run_skills("feishu", {"action": "get_auth_url"}) - 获取授权URL
2. 访问URL并授权，获取授权码
3. run_skills("feishu", {"action": "exchange_user_token", "code": "授权码"}) - 交换Token
4. run_skills("feishu", {"action": "search_wiki", "query": "关键词"})

检查用户Token: run_skills("feishu", {"action": "check_user_token"})

刷新用户Token: run_skills("feishu", {"action": "refresh_user_token"})
