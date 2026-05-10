# Plan: Gateway Enhancement ✅ (已完成)

## Step 1: Streaming 支持 ✅

**涉及文件**: `gateway.py`

- fastapi 返回 `StreamingResponse`
- 使用 `client.chat.completions.create(stream=True)` 迭代 chunks
- 每个 chunk 以 `data: {...}\n\n` 格式 SSE 发送
- 最后一个 chunk 发送 `data: [DONE]`
- **同时**：在内存中拼接完整 response，结束时写入 MLflow

## Step 2: Tool Calling ✅

**涉及文件**: `gateway.py` + `tools/` 目录

- 检测 response 中的 `tool_calls` 字段
- 注册可用的 tool 函数
- LLM 请求 tool → Gateway 执行 → 结果作为新的 message 发回 LLM
- 循环直到 LLM 返回纯文本回答（最多 10 轮）

## Step 3: 限流 ✅

**涉及文件**: `gateway.py`

- asyncio.Semaphore 并发控制
- 基于 IP 的滑动窗口限流
- 超出时返回 429

## Step 4: 模型列表 ✅

**涉及文件**: `gateway.py`

- `GET /v1/models` 调用 Ollama 的 `/api/tags`
- 转换为 OpenAI-compatible 格式

## Step 5: MCP Stdio ✅

**涉及文件**: `tools/mcp/` (新目录)

- 通过 npx/uvx 启动外部 MCP server
- JSON-RPC over stdin/stdout 通信
- 工具名自动加 server 前缀避免冲突

## Step 6: Trace 导出 ✅

**涉及文件**: `gateway.py`

- 非 streaming 请求完成后自动导出 trace 到 `mlruns/`

## 依赖

- 无新依赖（httpx / fastapi / asyncio 已有）
