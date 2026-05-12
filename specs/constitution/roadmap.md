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

## Phase 2: Agent Core ✅ (已完成)

- [x] Session 管理 (多对话隔离 + SQLite 持久化)
- [x] System Prompt 注入 (Persona / Instructions)
- [x] Skills 系统 (按需加载能力，注入到 prompt)
- [x] 记忆管理 (短期 context window + 长期持久化)

## Phase 3: Channel Adapters ✅ (已完成)

- [x] Telegram Bot 接入
- [ ] Slack Bot 接入 (低优先级，暂未实现)
- [x] Web Chat (简单的 HTML/JS)
- [x] 统一的 Channel Router

## Phase 4: Skills 增强 & 沙箱 (部分完成)

- [ ] Skills 市场 / 社区共享
- [x] Skills Registry & Prompt 注入 ✅ 完成
- [x] 沙箱执行 (Docker) ✅ SandboxExecutor 实现
- [x] 工具组合编排 (多工具联动) ✅ WorkflowEngine 实现
- [x] 子代理委托 (Agent Executor) ✅ 三种代理类型实现

## Phase 5: Canvas & 可视化 (部分完成)

- [x] CanvasManager (队列管理) ✅ 完成
- [x] SSE 实时推送 ✅ CanvasChannel 实现
- [ ] Agent-driven Web UI (完整交互)
- [x] Lab Website ✅ 首页、团队、论文等页面完成

## Phase 7: Agent增强 ✅ (已完成)

- [x] Fork机制 - context继承 + cache共享 ✅ 完成
- [x] Auto-compaction - 防止context爆炸 ✅ 完成
- [x] Token Budget追踪 ✅ 完成
- [x] 多层错误恢复 ✅ 完成
- [x] Permission系统 ✅ 完成
- [x] Hooks系统 ✅ 完成
- [x] Goal Command - 可衡量目标追踪（Stop hook机制） ✅ 完成

## Phase 8: Agent构建 App

- [ ] 用 AgentCraft 自身去生成一个实际应用
- [ ] 验证整个闭环

---

> 每个 Phase 产出可运行的代码，可以单独使用。不依赖后续 Phase。
