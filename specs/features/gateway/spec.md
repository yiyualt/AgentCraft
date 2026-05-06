# Feature: Ollama Gateway

## 背景

当前 gateway.py 是一个简单的请求代理，不支持 streaming，也没有 tool calling 能力。

## 目标

- [ ] 支持 OpenAI-compatible streaming (`stream=true`)
- [ ] 支持 Tool Calling 转发（LLM 请求工具 → Gateway 执行 → 返回结果给 LLM）
- [ ] 请求限流 / 并发控制（防止 Ollama OOM）
- [ ] 模型列表 API (`GET /v1/models`)
- [ ] 更好的错误处理和超时管理

## 非目标

- 用户认证/鉴权（个人使用，不需要）
- 多用户隔离
- 高可用/负载均衡

## 接口

保持与 OpenAI Chat Completions API 兼容：
- `POST /v1/chat/completions`
- `GET /v1/models`
- `GET /health`

## Streaming 设计

```
Client → Gateway → Ollama (streaming)
         Gateway ← Ollama (SSE chunks)
Client ← Gateway ← (转发每个 chunk，同时记录到 MLflow)
```

- 每个 chunk 透传，不修改 content
- 最终汇总完整 response 记录到 MLflow
