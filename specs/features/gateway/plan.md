# Plan: Gateway Enhancement

## Step 1: Streaming 支持

**涉及文件**: `gateway.py`

- fastapi 返回 `StreamingResponse`
- 使用 `client.chat.completions.create(stream=True)` 迭代 chunks
- 每个 chunk 以 `data: {...}\n\n` 格式 SSE 发送
- 最后一个 chunk 发送 `data: [DONE]`
- **同时**：在内存中拼接完整 response，结束时写入 MLflow

## Step 2: Tool Calling

**涉及文件**: `gateway.py` (+ 新的 `tools/` 目录)

- 检测 response 中的 `tool_calls` 字段
- 注册可用的 tool 函数
- LLM 请求 tool → Gateway 执行 → 结果作为新的 message 发回 LLM
- 循环直到 LLM 返回纯文本回答

## Step 3: 限流

**涉及文件**: `gateway.py`

- 简单计数器 / asyncio.Semaphore
- 最大并发请求数可配置（默认 1）
- 超出时返回 429

## Step 4: 模型列表

**涉及文件**: `gateway.py`

- `GET /v1/models` 调用 Ollama 的 `/api/tags` 获取模型列表
- 转换为 OpenAI-compatible 格式返回

## 依赖

- 无新依赖（httpx / fastapi 已有）
