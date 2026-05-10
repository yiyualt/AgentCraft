# Plan: Session Management

## Step 1: 数据模型

**涉及文件**: `sessions/models.py` (新建)

- `Session` dataclass: id, name, model, system_prompt, created_at, updated_at, message_count, token_count, status
- `Message` dataclass: id, session_id, role, content, tool_calls, created_at
- 用 `sqlite3` (内置) 建表，不引入 ORM

## Step 2: SessionManager

**涉及文件**: `sessions/manager.py` (新建)

```
class SessionManager:
    create_session(name, model, system_prompt) → Session
    get_session(session_id) → Session | None
    list_sessions(status=None) → list[Session]
    update_session(session_id, **kwargs) → Session
    delete_session(session_id) → None
    archive_session(session_id) → None

    add_message(session_id, role, content, tool_calls) → Message
    get_history(session_id, limit=None) → list[Message]
    clear_history(session_id) → None
    count_tokens(session_id) → int
```

- 数据库路径: `~/.agentcraft/sessions.db`
- 所有方法返回 dataclass，内部用 dict cursor

## Step 3: Gateway 端点

**涉及文件**: `gateway.py`

```
POST   /v1/sessions              创建会话
GET    /v1/sessions              列出会话
GET    /v1/sessions/{session_id}  获取会话详情
PATCH  /v1/sessions/{session_id}  更新会话（名称、system_prompt）
DELETE /v1/sessions/{session_id}  删除会话

GET    /v1/sessions/{session_id}/messages  获取历史消息
DELETE /v1/sessions/{session_id}/messages  清除历史
```

- 在 startup 事件中初始化 SessionManager
- 非 streaming 请求自动记录消息到 session
- 通过 `X-Session-Id` header 或 `session_id` 参数指定会话

## Step 4: chat.py 集成

**涉及文件**: `chat.py`

- 支持 `--session` 参数指定会话名
- 启动时列出可用会话
- `/new` 命令创建新会话
- `/sessions` 命令列出会话
- 退出时自动保存

## 依赖

- 无新依赖（sqlite3 内置）