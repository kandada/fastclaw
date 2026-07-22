## Description
Feishu (Lark) skill — send messages, create/read/edit/share cloud documents, search the wiki, and manage OAuth tokens.

## Parameters
- action: operation type (required)
  - send: send a message
  - create_doc: create a cloud document
  - get_doc: get document metadata
  - read_doc: read document content
  - append_doc: append content to a document block
  - update_doc: update a document block
  - list_files: list cloud drive files
  - create_folder: create a folder
  - share_doc: share a document with a member
  - search_wiki: search the knowledge base (requires user authorization)
  - get_auth_url: get OAuth authorization URL
  - exchange_user_token: exchange authorization code for user token
  - refresh_user_token: refresh user token
  - check_user_token: check user token status

### send params
- message: message content (required)
- session_id: feishu user open_id (required)

### create_doc params
- title: document title (optional, default "Untitled Document")
- folder_token: parent folder token (optional)

### get_doc params
- document_id: document token (required)

### read_doc params
- document_id: document token (required)

### append_doc params
- document_id: document token (required)
- block_id: parent block ID (optional, default appends to document root)
- content: content (required)
- block_type: block type (optional, default 2 = text block)

### update_doc params
- document_id: document token (required)
- block_id: block ID (required)
- content: new content (required)

### list_files params
- folder_token: folder token (optional, lists root if omitted)
- page_size: page size (optional, default 50)

### create_folder params
- name: folder name (required)
- folder_token: parent folder token (optional)

### share_doc params
- document_id: document token (required)
- member_id: member ID (required)
- member_type: member type (optional, default "openid")
- share_type: permission type (optional, default "edit", can be "full_access")

### search_wiki params
- query: search keyword (required)
- count: number of results (optional, default 10)
- Note: requires authorization via get_auth_url and exchange_user_token first

### exchange_user_token params
- code: authorization code (required, obtained from the callback URL parameter)

## Example
Send message: run_skills("feishu", {"action": "send", "message": "Hello", "session_id": "ou_xxx"})

Create doc: run_skills("feishu", {"action": "create_doc", "title": "My Document"})

Get doc: run_skills("feishu", {"action": "get_doc", "document_id": "xxx"})

Read doc: run_skills("feishu", {"action": "read_doc", "document_id": "xxx"})

Append content: run_skills("feishu", {"action": "append_doc", "document_id": "xxx", "content": "New paragraph"})

Update block: run_skills("feishu", {"action": "update_doc", "document_id": "xxx", "block_id": "yyy", "content": "Updated content"})

List files: run_skills("feishu", {"action": "list_files"})

Create folder: run_skills("feishu", {"action": "create_folder", "name": "New Folder"})

Share doc: run_skills("feishu", {"action": "share_doc", "document_id": "xxx", "member_id": "ou_xxx", "share_type": "edit"})

Search wiki (requires authorization):
1. run_skills("feishu", {"action": "get_auth_url"})
2. Visit the URL and authorize, get the authorization code
3. run_skills("feishu", {"action": "exchange_user_token", "code": "<code>"})
4. run_skills("feishu", {"action": "search_wiki", "query": "keyword"})

Check user token: run_skills("feishu", {"action": "check_user_token"})

Refresh user token: run_skills("feishu", {"action": "refresh_user_token"})
