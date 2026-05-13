## Why

当前 AgentCraft 只有 HTTP API 形式（gateway.py），用户需要通过浏览器 UI 或 curl 调用。对于本地开发场景，CLI 形式更方便：直接在终端中与 agent 交互，无需启动服务器，类似于 Claude Code 的使用体验。

同时，CLI 形式可以：
- 直接运行单个任务（one-shot mode）
- 交互式 REPL 模式持续对话
- 方便集成到 CI/CD 流程中

## What Changes

- 新增 `cli.py` 入口点，支持终端交互
- 支持两种模式：
  - **One-shot**: `agentcraft "分析代码结构"` — 执行单个任务后退出
  - **Interactive**: `agentcraft --interactive` — 进入 REPL 模式持续对话
- 支持命令行参数：model、session、skills、permission mode
- 集成现有的 StreamingToolExecutor，实时显示工具执行进度
- 支持 Slash 命令（/goal, /permission, /hook）
- 支持流式输出（实时显示 LLM 响应）

## Capabilities

### New Capabilities

- `cli-interface`: CLI 入口点和交互式终端界面

### Modified Capabilities

- `gateway`: 新增 `--cli` 启动模式（可选，或保持 CLI 与 Gateway 独立）
- `sessions`: CLI 模式下的 session 管理（内存模式，可选持久化）

## Impact

**新增文件**：
- `cli.py` — CLI 入口点
- `terminal_ui.py` — Terminal UI 渲染（可选，如果使用 rich/textual）

**依赖**：
- 可选：`rich` 或 `textual` 用于 Terminal UI（或纯文本输出）

**使用示例**：
```bash
# One-shot mode
agentcraft "帮我写一个 FastAPI 应用"

# Interactive mode
agentcraft -i --model deepseek-chat --session dev-session

# With skills
agentcraft "生成PPT" --skill pptx-generator

# CI/CD integration
agentcraft "检查代码是否有安全漏洞" --permission bypass --json
```