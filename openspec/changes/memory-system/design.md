## Context

当前 AgentCraft 只有对话内存管理（`sessions/memory.py`），包含滑动窗口和摘要策略。这些策略用于**压缩对话历史**，但不会**持久化跨会话信息**。

Claude Code 的记忆系统设计：
- 存储位置: `~/.claude/projects/<project-hash>/memory/`
- 文件格式: Markdown + YAML frontmatter
- 记忆类型: user, feedback, project, reference
- 加载时机: 会话开始时静默加载到 context
- 保存时机: 用户显式请求 + LLM 自动提取

我们需要实现类似系统，适配 AgentCraft 的架构。

## Goals / Non-Goals

**Goals:**
- 实现四种记忆类型的持久化存储
- 支持从对话中自动提取记忆（LLM分析）
- 支持用户显式保存/删除记忆
- 记忆文件人类可读（Markdown格式）
- 记忆间支持链接引用 `[[memory-name]]`

**Non-Goals:**
- 不实现记忆版本控制（保留简单）
- 不实现记忆搜索功能（文件系统足够）
- 不实现记忆过期机制（用户手动删除）

## Decisions

### D1: 存储位置

**决定**: `~/.agentcraft/projects/<project-path-hash>/memory/`

**理由**:
- 项目级隔离：不同项目不同记忆
- path-hash 避免 clash（如多个同名项目）
- 与 Claude Code 一致，便于用户理解

**备选方案**:
- `~/.agentcraft/memory/` (全局) - ❌ 不同项目记忆冲突
- `.agentcraft/memory/` (项目内) - ❌ 删除项目丢失记忆

### D2: 文件格式

**决定**: Markdown + YAML frontmatter

```markdown
---
name: user-role
description: one-line summary
metadata:
  type: user
---

记忆内容...
**Why:** 原因
**How to apply:** 应用方式
```

**理由**:
- 人类可读，可手动编辑
- YAML frontmatter 支持元数据查询
- 与 Claude Code 一致

### D3: 记忆索引

**决定**: `MEMORY.md` 作为索引文件

**理由**:
- 类似 README，快速浏览所有记忆
- 避免 glob 扫描所有文件
- 限制 ~200 行（加载到 context）

### D4: 自动提取时机

**决定**: 会话结束时分析，不实时提取

**理由**:
- 避免每轮对话都调用 LLM 分析（开销大）
- 会话结束时整段分析更准确
- 用户可手动触发提取（`/remember` 命令）

**备选方案**:
- 实时提取每轮对话 - ❌ 太频繁，成本高
- 不自动提取，只手动 - ❌ 用户忘记保存

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| 记忆文件膨胀 | MEMORY.md 限制200行，超时截断 |
| 记忆内容陈旧 | 用户手动删除，或在 MEMORY.md 标注日期 |
| LLM提取错误 | 提取后让用户确认（可选） |
| 记忆加载占用 context | 索引文件简短，正文按需加载 |

## Implementation Overview

``sessions/memory_persistence.py``:
- `MemoryType` enum (user, feedback, project, reference)
- `MemoryEntry` dataclass (name, description, type, content, created_at)
- `MemoryStore` class (save, load, list, delete, link)
- `MemoryExtractor` class (LLM-based extraction from conversation)
- `MEMORY.md` index generator

``tools/memory_tools.py``:
- `remember` tool - 显式保存记忆
- `forget` tool - 删除记忆
- `recall` tool - 查询记忆

Integration:
- `gateway.py`: startup 时加载 MEMORY.md 到 context
- `cli.py`: `/remember`, `/forget`, `/recall` 命令
- 会话结束时调用 `MemoryExtractor.extract()`