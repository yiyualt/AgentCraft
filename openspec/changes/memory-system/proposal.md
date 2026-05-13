## Why

AgentCraft 当前缺少跨会话记忆能力。每次对话都从零开始，无法记住用户的偏好、之前给出的反馈、项目上下文等关键信息。这导致用户体验碎片化，需要重复解释背景，效率低下。

**核心问题**: 用户说"不要mock数据库测试"，下次对话agent又mock了；用户是资深Go工程师但第一次接触React，每次都需要重新解释背景。

## What Changes

新增文件持久化记忆系统，支持四种记忆类型：

- **user**: 用户角色、偏好、知识水平、工作方式
- **feedback**: 用户给出的行为指导（"不要做X"、"保持做Y")
- **project**: 项目级上下文、决策原因、约束条件
- **reference**: 外部资源指针（Linear项目、Slack频道、文档链接）

记忆存储在 `~/.agentcraft/projects/<project-path>/memory/` 目录下，以 Markdown 文件形式保存，包含 YAML frontmatter。

**关键特性**:
- 自动从对话中提取记忆（LLM分析）
- 静默加载（不打扰用户）
- 用户显式请求时立即保存
- 支持遗忘（删除特定记忆）
- 记忆间可链接引用

## Capabilities

### New Capabilities

- `memory-system`: 文件持久化记忆系统，包含记忆类型定义、存储格式、提取逻辑、加载机制

## Impact

**新增文件**:
- `sessions/memory_persistence.py` - 记忆持久化核心模块
- `tools/memory_tools.py` - 记忆操作工具（供用户显式调用）

**修改文件**:
- `gateway.py` - 集成记忆加载和保存逻辑
- `cli.py` - 添加记忆相关命令
- `sessions/__init__.py` - 导出新模块
- `pyproject.toml` - 新增工具包路径

**API变更**:
- 新增 `POST /memory/save` 端点
- 新增 `GET /memory/list` 端点
- 新增 `DELETE /memory/{name}` 端点