# Feature: Ollama Gateway

## 背景

Gateway 是 AgentCraft 的核心入口，提供 OpenAI-compatible API，代理请求到本地 Ollama，
同时集成 MLflow 追踪、工具调用编排、MCP 外部工具接入。

## 目标

- [ ] 支持 OpenAI-compatible streaming (`stream=true`) — **未实现**
- [x] 支持 Tool Calling 转发（LLM 请求工具 → Gateway 执行 → 返回结果给 LLM）
- [x] 请求限流 / 并发控制（防止 Ollama OOM）
- [x] 模型列表 API (`GET /v1/models`)
- [x] MCP Stdio 支持（启动外部 MCP server 并调用其工具）
- [x] Trace 自动导出到文件系统

## 非目标

- 用户认证/鉴权（个人使用，不需要）
- 多用户隔离
- 高可用/负载均衡

## 接口

保持与 OpenAI Chat Completions API 兼容：
- `POST /v1/chat/completions` — 聊天补全（stream 和 non-stream）
- `GET /v1/models` — 列出可用模型
- `GET /health` — 健康检查

## 架构

```
Client → Gateway (FastAPI)
           ├─→ Ollama (LLM 推理)
           ├─→ ToolRegistry (本地工具)
           ├─→ MCP Servers (外部工具，通过 stdio)
           └─→ MLflow (追踪)
```
