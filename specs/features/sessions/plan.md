# Plan: Session Management

## Step 1: 数据模型 ✅

**涉及文件**: `sessions/models.py` (新建)

- `Session` dataclass: id, name, model, system_prompt, created_at, updated_at, message_count, token_count, status
- `Message` dataclass: id, session_id, role, content, tool_calls, tool_call_id, name, created_at
- 用 `sqlite3` (内置) 建表，不引入 ORM

## Step 2: SessionManager ✅

**涉及文件**: `sessions/manager.py` (新建)

```
class SessionManager:
    create_session(name, model, system_prompt) → Session
    get_session(session_id) → Session | None
    list_sessions(status="active") → list[Session]
    update_session(session_id, **fields) → Session
    delete_session(session_id) → bool

    add_message(session_id, role, content, tool_calls, tool_call_id, name) → Message
    get_messages(session_id, limit=50) → list[Message]
    get_messages_openai(session_id, limit=50) → list[dict]
    clear_messages(session_id) → None
    count_tokens(session_id) → int
```

- 数据库路径: `~/.agentcraft/sessions.db`
- 所有方法返回 dataclass

## Step 3: Gateway 端点 ✅

**涉及文件**: `gateway.py`

```
POST   /v1/sessions              创建会话
GET    /v1/sessions              列出会话
GET    /v1/sessions/{id}         获取会话详情
PATCH  /v1/sessions/{id}         更新会话
DELETE /v1/sessions/{id}         删除会话
GET    /v1/sessions/{id}/messages 获取历史消息
```

- 在模块级别初始化 SessionManager
- `_handle_non_streaming`: 通过 `X-Session-Id` header 自动加载历史、保存消息
- `_handle_streaming`: 同样支持 session 上下文注入和消息持久化

## Step 4: chat.py 集成 ✅

**涉及文件**: `chat.py`

- 支持 `--session` 参数指定会话名（不存在则自动创建）
- `/sessions` 命令列出所有会话
- `/new <name>` 命令创建新会话并切换
- `/clear` 清空当前会话历史
- 每条用户消息和 assistant 回复自动持久化

## 依赖

- 无新依赖（sqlite3 内置）
