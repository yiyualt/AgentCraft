## Context

**ollama-mlflow-demo** (当前仓库) 是一个轻量级的 AI Agent Gateway 实现，专注于：
- FastAPI Gateway 提供统一的 API 入口
- MLflow 集成用于追踪和实验管理
- 流式工具执行（streaming_executor.py）
- 多通道支持（Telegram、Web）
- Session 管理、权限控制、记忆持久化

**Hermes-Agent** 是 Nous Research 开发的生产级 AI Agent 框架，具有：
- 自我学习闭环（技能创建、记忆建模）
- 多平台消息网关（20+ 平台）
- 完整的 CLI 和 TUI
- 批量轨迹生成和 RL 训练环境
- 六种终端后端

## Goals / Non-Goals

**Goals:**
- 完成两个仓库架构的全面对比分析
- 识别关键差异和各自优势
- 提出可借鉴的架构模式

**Non-Goals:**
- 不直接进行代码迁移或重构
- 不改变当前仓库的架构
- 不涉及具体实现方案

## Decisions

### 1. 代码规模对比

| 指标 | ollama-mlflow-demo | Hermes-Agent |
|------|---------------------|--------------|
| Python 文件数 | ~1,215 | ~12,738 (10x) |
| 核心文件行数 | gateway.py: 1,441 | run_agent.py: 13,215 (9x) |
| CLI 行数 | cli.py: 584 | cli.py: 11,387 (19x) |
| Session 存储 | hermes_state.py: 1,811 | sessions/*.py: ~15 个模块 |

**结论**: Hermes 代码规模约 10 倍，架构更成熟复杂。

### 2. 核心 Agent 实现对比

**ollama-mlflow-demo (gateway.py)**
- FastAPI 为核心，HTTP API 入口
- OpenAI SDK 作为 LLM 客户端
- StreamingToolExecutor 提供并行工具执行
- 简化的对话循环

**Hermes-Agent (run_agent.py)**
- AIAgent 类为核心（约 60 个参数）
- 多 Provider 适配器（Anthropic、Gemini、Bedrock、Codex）
- IterationBudget 控制迭代次数
- 并发安全工具分类（PARALLEL_SAFE_TOOLS、PATH_SCOPED_TOOLS）
- 轨迹压缩和保存
- 完整的错误分类和恢复机制

**差异**: Hermes 的 Agent 实现更完善，支持多模型适配、预算控制、轨迹管理。

### 3. Session 管理对比

**ollama-mlflow-demo (sessions/*.py)**
- SQLite 存储
- TokenCalculator 计算预算
- CompactionManager 压缩策略
- SlidingWindowStrategy / SummaryStrategy / HybridStrategy
- ForkManager 会话分支
- BudgetManager 预算控制
- PermissionChecker 权限控制（~24k 行）
- MemoryStore 记忆持久化

**Hermes-Agent (hermes_state.py)**
- SQLite + WAL 模式
- FTS5 全文搜索
- Session 分裂链（parent_session_id）
- Schema 版本管理
- 线程安全设计
- 写入重试和随机抖动

**差异**: Hermes 有 FTS5 搜索能力，Session 分裂机制；我们有更完善的权限和预算系统。

### 4. 工具系统对比

**ollama-mlflow-demo (tools/*.py)**
- ToolRegistry 装饰器注册
- UnifiedToolRegistry 合并 MCP
- 并发安全分类（streaming_executor.py）
- 内置工具：builtin.py, pptx_tools.py, canvas_tools.py, memory_tools.py
- MCP 集成

**Hermes-Agent (tools/*.py, model_tools.py)**
- 自动发现注册
- Toolsets 系统（toolsets.py）
- 并发安全分类
- 审批机制（approval.py）
- 浏览器工具（browser_tool.py, 115k 行）
- 终端后端（environments/）
- 委托工具（delegate_tool.py, 103k 行）

**差异**: Hermes 工具更丰富，有终端后端系统、委托机制；我们更简洁。

### 5. Skills 系统

**ollama-mlflow-demo (skills/*.py)**
- SkillLoader 加载技能
- SkillRegistry 注册
- 内置技能（skills/builtin/）
- 技能打包

**Hermes-Agent (skills/*, optional-skills/*)**
- 27 个技能目录（apple, github, mlops, research...）
- Skills Hub 集成
- agentskills.io 标准兼容
- 技能自改进机制

**差异**: Hermes 技能库规模更大，有自改进循环。

### 6. Gateway/消息平台

**ollama-mlflow-demo (channels/*.py)**
- Telegram
- Web
- Canvas
- ChannelRouter 路由

**Hermes-Agent (gateway/platforms/*.py)**
- 30+ 平台：Telegram、Discord、Slack、WhatsApp、Signal、Matrix、HomeAssistant、Email、SMS、Dingtalk、Feishu、Wecom、Weixin、QQBot...
- 完整的适配器基类（base.py, 116k 行）
- 每个平台独立实现（telegram.py 138k 行）

**差异**: Hermes 平台覆盖远超我们，有完整的消息网关系统。

### 7. 权限与安全

**ollama-mlflow-demo (sessions/permission.py)**
- PermissionMode（accept-all, accept-edits, plan-mode...）
- MultiSourceRuleManager 多源规则
- PermissionAuditor 审计日志
- YoloClassifier 分类
- HookExecutor 钩子执行

**Hermes-Agent (tools/approval.py)**
- 审批回调机制
- sudo 密码回调
- 终端安全分类
- 文件安全检查

**差异**: 我们权限系统更完善；Hermes 更侧重终端审批。

### 8. 记忆系统

**ollama-mlflow-demo (sessions/memory_persistence.py)**
- MemoryType（user, feedback, project, reference）
- MemoryStore 持久化
- MemoryExtractor 提取
- MEMORY.md 索引

**Hermes-Agent (agent/memory_manager.py, plugins/memory/)**
- Honcho 用户建模
- 记忆提供者插件
- Agent 自我 nudges
- FTS5 会话搜索

**差异**: Hermes 有 Honcho 集成和自我 nudges；我们有结构化记忆类型。

## Risks / Trade-offs

**借鉴风险**:
- Hermes 功能丰富但复杂度高，直接移植可能过度
- 部分功能需要配套基础设施（如 Honcho、Daytona）

**Trade-offs**:
- 我们架构更轻量，适合快速迭代
- Hermes 更适合生产级部署和大规模使用

**建议借鉴顺序**:
1. FTS5 搜索能力（高价值，低风险）
2. Session 分裂机制（解决压缩问题）
3. 工具并发安全分类（已有类似实现）
4. 终端后端系统（需要基础设施）
5. 委托工具机制（架构变动大）