# Validation: Gateway Enhancement

## 手动测试

```bash
# 1. Streaming
curl -N http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"你好"}],"stream":true}'

# 2. 模型列表
curl http://127.0.0.1:8000/v1/models

# 3. Health
curl http://127.0.0.1:8000/health
```

## 验证清单

- [x] `stream=false` 保持现有行为不变（回归测试）
- [x] `stream=true` 返回 SSE 格式，最后一个 chunk 为 `[DONE]`
- [x] 并发请求超过限制返回 429
- [x] MLflow 记录 streaming 请求的完整 response
- [x] Tool calling 循环正确执行（最多 10 轮）
- [x] MCP server 工具可被 LLM 调用
- [x] Trace 导出到 mlruns 文件系统
