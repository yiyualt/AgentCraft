# Validation: Session Management

## 手动测试

```bash
# 1. 创建会话
curl -X POST http://127.0.0.1:8000/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"name":"test","model":"qwen3:8b","system_prompt":"你是一个助手"}'

# 2. 列出会话
curl http://127.0.0.1:8000/v1/sessions

# 3. 获取会话详情
curl http://127.0.0.1:8000/v1/sessions/{session_id}

# 4. 在会话中聊天
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Session-Id: {session_id}" \
  -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"你好"}]}'

# 5. 获取历史消息
curl http://127.0.0.1:8000/v1/sessions/{session_id}/messages

# 6. 归档会话
curl -X PATCH http://127.0.0.1:8000/v1/sessions/{session_id} \
  -H "Content-Type: application/json" \
  -d '{"status":"archived"}'

# 7. 删除会话
curl -X DELETE http://127.0.0.1:8000/v1/sessions/{session_id}
```

## 验证清单

- [ ] 创建会话返回 UUID，可查询
- [ ] 多会话之间消息隔离
- [ ] 会话归档后仍在列表中但标记状态
- [ ] 删除会话并清除关联消息
- [ ] 通过 X-Session-Id 聊天，消息自动记录
- [ ] 不指定 session 时行为不变（回归测试）
- [ ] 重启 Gateway 后会话和消息仍在（SQLite 持久化）
- [ ] chat.py --session 可恢复之前对话