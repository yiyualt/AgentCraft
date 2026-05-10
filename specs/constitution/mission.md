# Mission: AgentCraft

## 一句话愿景

从本地大模型出发，逐步搭建一个**个人 AI 助手**，最终利用这个 AI 助手去**构建真正的应用**。

## 核心原则

1. **本地优先 (Local-First)** — 所有核心能力运行在自己的设备上，数据不出门
2. **增量演进 (Incremental)** — 每个阶段产出可运行的、可验证的东西，不是纯设计文档
3. **学习驱动 (Learning-Driven)** — 不追求一次完美，每个阶段填补一块知识空白
4. **可观测 (Observable)** — 所有 Agent 行为通过 MLflow / 日志可追溯

## 学习路径

```
阶段 0: Local LLM 基础 ✅
      ↓
阶段 1: Gateway + Tool Calling + MCP ✅
      ↓
阶段 2: Agent Core (Session + Skills + Memory)  ← 你在这里
      ↓
阶段 3: Channel Adapters (Telegram / Slack / Web)
      ↓
阶段 4: Skills 增强 + 沙箱执行
      ↓
阶段 5: Canvas / Visual Workspace
      ↓
阶段 6: 用 Agent 去构建真正的 App
```

## 参照目标

[OpenClaw](https://github.com/openclaw/openclaw) — 一个自托管的个人 AI 助手。

> **注意**: 我们不直接 clone OpenClaw 的代码，而是**理解其架构后用自己的方式实现**。这是一个学习过程，不用于商业用途。
