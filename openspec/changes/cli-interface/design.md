## Context

当前 AgentCraft 只有 HTTP API（gateway.py），需要启动服务器才能使用。用户想要类似 Claude Code 的 CLI 体验：
- 直接在终端运行
- 无需启动服务器
- 交互式 REPL 或 one-shot 模式

CLI 将复用现有的核心组件：
- `UnifiedToolRegistry` — 工具执行
- `SessionManager` — 会话管理
- `StreamingToolExecutor` — 并发工具执行
- `AgentExecutor` — Sub-agent delegation

## Goals / Non-Goals

**Goals:**
- One-shot 模式：`agentcraft "任务"` 执行后退出
- Interactive REPL 模式：持续对话
- 实时显示工具执行进度（使用 StreamingToolExecutor）
- 支持 Slash 命令（/goal, /permission）
- 流式输出 LLM 响应

**Non-Goals:**
- 不实现复杂的 TUI（如 Claude Code 的 TUI）
- 不实现 MCP server 启动（CLI 连接到已运行的 gateway 或直接调用 API）
- 不实现工作目录切换（git worktree）

## Decisions

### Decision 1: CLI 与 Gateway 关系

**选择**: CLI 作为独立入口点，直接调用 LLM API 和工具执行逻辑

**替代方案**:
1. CLI 作为 gateway 的 client（需要 gateway 运行）
2. CLI 直接调用 LLM（无需 gateway）

**理由**: 选择方案2
- 用户无需启动 gateway
- 更接近 Claude Code 的体验
- 复用 gateway.py 的核心逻辑（SessionManager, StreamingToolExecutor）

### Decision 2: Terminal UI 库

**选择**: 使用 `rich` 库进行简单渲染

**替代方案**:
1. 纯文本输出（无依赖）
2. `textual`（完整 TUI）

**理由**: 选择 `rich`
- 简单但有美观输出
- 支持进度条、表格、markdown 渲染
- 不需要复杂 TUI 功能

### Decision 3: Session 管理

**选择**: 内存模式 + 可选持久化到文件

**替代方案**:
1. 无 session（每次调用独立）
2. 强制持久化到 SQLite

**理由**: 选择内存+可选持久化
- One-shot 模式无需持久化
- Interactive 模式可选持久化（`--session <name>` 参数）
- 简化实现

### Decision 4: 流式输出

**选择**: 使用 LLM streaming API + 逐字输出

**替代方案**:
1. 等待完整响应后输出

**理由**: 选择 streaming
- 更好的用户体验
- Claude Code 也使用 streaming

## Risks / Trade-offs

**Risk: CLI 直接调用 LLM API，无 gateway 的 rate limiting 保护**
→ Mitigation: CLI 实现简单的 rate limiting（可选）

**Risk: 工具执行可能耗时较长，阻塞 CLI**
→ Mitigation: 使用 StreamingToolExecutor 并行执行 + 进度显示

**Trade-off: 不实现完整 TUI**
→ 用户可能在复杂场景下体验不如 Claude Code，但实现成本低

## Implementation Outline

```
cli.py (入口点)
├── main() — argparse 参数解析
├── run_one_shot() — 执行单个任务
├── run_interactive() — REPL 模式
└── terminal_ui.py — Rich 渲染辅助

复用组件:
├── SessionManager (内存模式)
├── StreamingToolExecutor (并发工具执行)
├── UnifiedToolRegistry (工具调用)
└── SkillLoader (技能加载)
```