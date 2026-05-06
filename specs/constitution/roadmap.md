# Roadmap — AgentCraft

## Phase 0: Foundation ✅ (已完成)

- [x] 基础 chat.py (REPL 交互)
- [x] FastAPI Gateway (请求代理 + MLflow)
- [x] 项目结构 (pyproject.toml, uv)

## Phase 1: Gateway 强化

- [ ] 支持 streaming 响应
- [ ] Tool Calling 代理 (将 LLM 的 tool calls 转发回 Gateway 执行)
- [ ] 请求限流 / 并发控制
- [ ] 健康检查 + 模型列表 API

## Phase 2: Agent Core

- [ ] Session 管理 (多对话隔离)
- [ ] System Prompt 注入 (Persona / Instructions)
- [ ] Tool Registry (注册、发现、执行工具)
- [ ] 记忆管理 (短期 context window + 长期持久化)

## Phase 3: Channel Adapters

- [ ] Telegram Bot 接入
- [ ] Slack Bot 接入
- [ ] Web Chat (简单的 HTML/JS)
- [ ] 统一的 Channel Router

## Phase 4: Skills & Tools

- [ ] Skills 系统 (按需加载能力)
- [ ] MCP 工具协议支持
- [ ] 沙箱执行 (Docker)
- [ ] 工具市场 / ClawHub 类似物

## Phase 5: Canvas & 可视化

- [ ] Agent-driven Web UI
- [ ] Live Canvas (实时更新)
- [ ] 文件/图片/代码渲染

## Phase 6: Agent 构建 App

- [ ] 用 AgentCraft 自身去生成一个实际应用
- [ ] 验证整个闭环

---

> 每个 Phase 产出可运行的代码，可以单独使用。不依赖后续 Phase。
