# Feature: Session Management

## 背景

当前 chat.py 每次启动只维护一个内存中的对话列表。退出后历史丢失。无法同时管理多个对话。

## 目标

- [ ] 多会话支持（每个 session 有独立 ID 和对话历史）
- [ ] 会话持久化（SQLite）
- [ ] 会话生命周期管理（创建、切换、归档、删除）
- [ ] 会话元数据（模型、system prompt、创建时间、token 数）

## 设计

```
Session {
  id: UUID
  name: str
  model: str
  system_prompt: str | None
  created_at: datetime
  updated_at: datetime
  message_count: int
  token_count: int
  status: active | archived
}

Message {
  id: UUID
  session_id: UUID
  role: user | assistant | system | tool
  content: str
  tool_calls: list | None
  created_at: datetime
}
```

## 接口

```python
class SessionManager:
    def create_session(...) -> Session
    def get_session(id) -> Session
    def list_sessions() -> list[Session]
    def delete_session(id) -> None
    def add_message(session_id, message) -> Message
    def get_history(session_id) -> list[Message]
    def count_tokens(session_id) -> int
```
