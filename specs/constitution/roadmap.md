# Roadmap — AgentCraft

## Phase 0: Foundation ✅ (已完成)

- [x] 基础 chat.py (REPL 交互)
- [x] FastAPI Gateway (请求代理 + MLflow)
- [x] 项目结构 (pyproject.toml, uv)

## Phase 1: Gateway 强化 ✅ (已完成)

- [x] 支持 streaming 响应
- [x] Tool Calling 代理 (将 LLM 的 tool calls 转发回 Gateway 执行)
- [x] 请求限流 / 并发控制
- [x] 健康检查 + 模型列表 API
- [x] MCP Stdio 支持 (通过 npx/uvx 启动外部 MCP server)

## Phase 2: Agent Core

- [x] Session 管理 (多对话隔离 + SQLite 持久化)
- [x] System Prompt 注入 (Persona / Instructions)
- [x] Skills 系统 (按需加载能力，注入到 prompt)
- [ ] 记忆管理 (短期 context window + 长期持久化)

## Phase 3: Channel Adapters

- [ ] Telegram Bot 接入
- [ ] Slack Bot 接入
- [ ] Web Chat (简单的 HTML/JS)
- [ ] 统一的 Channel Router

## Phase 4: Skills 增强 & 沙箱

- [ ] Skills 市场 / 社区共享
- [ ] 沙箱执行 (Docker)
- [ ] 工具组合编排 (多工具联动)

## Phase 5: Canvas & 可视化

- [ ] Agent-driven Web UI
- [ ] Live Canvas (实时更新)
- [ ] 文件/图片/代码渲染

## Phase 6: Agent 构建 App

- [ ] 用 AgentCraft 自身去生成一个实际应用
- [ ] 验证整个闭环

---

> 每个 Phase 产出可运行的代码，可以单独使用。不依赖后续 Phase。
