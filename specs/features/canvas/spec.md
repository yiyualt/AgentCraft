# Feature: Live Canvas

## 背景

OpenClaw 的 Canvas 是一个 "agent-driven visual workspace" — Agent 可以动态生成和更新 UI，用户可以与之交互。这是构建 "用 Agent 搭建 App" 这一终极目标的关键能力。

## 目标

- [ ] Agent 可以动态生成 UI 组件（HTML 片段）
- [ ] Canvas 实时更新（SSE / WebSocket）
- [ ] 用户可以与 Canvas 交互（点击、输入）
- [ ] A2UI (Agent-to-User Interface) 协议支持

## 设计（候选）

```
Agent → 生成 UI 描述 (JSON/HTML) → Canvas Server → Browser/Client
        ← 用户交互事件 ←           ← SSE push    ←
```

## 第一阶段（最小可行）

- 简单的 Web 页面，显示 Agent 的 "工作台"
- Agent 通过 tool call 更新工作台内容
- 工作台显示 Markdown / 代码 / 表格

## 后续

- 交互式组件（表单、按钮）
- 实时数据流可视化
- 拖拽交互
