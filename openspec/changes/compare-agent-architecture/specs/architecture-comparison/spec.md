## ADDED Requirements

### Requirement: 架构对比文档应包含代码规模分析
对比文档 SHALL 包含两个仓库的代码规模对比，包括：
- Python 文件总数
- 核心模块行数（Agent 实现、CLI、Session 存储）
- 模块数量对比

#### Scenario: 用户查看代码规模对比
- **WHEN** 用户打开架构对比文档
- **THEN** 可以看到两个仓库的文件数、核心代码行数的具体数据

### Requirement: 架构对比文档应包含核心 Agent 实现分析
对比文档 SHALL 包含两个仓库核心 Agent 实现的分析，包括：
- Agent 类/函数的设计差异
- LLM Provider 适配方式
- 对话循环实现
- 工具执行并发处理

#### Scenario: 用户了解 Agent 实现差异
- **WHEN** 用户查阅核心 Agent 实现章节
- **THEN** 可以看到两种实现方式的对比和各自特点

### Requirement: 架构对比文档应包含 Session 管理分析
对比文档 SHALL 包含 Session 管理系统的对比，包括：
- 存储方式（SQLite、文件）
- 压缩策略
- 搜索能力
- 分裂/分支机制

#### Scenario: 用户了解 Session 系统差异
- **WHEN** 用户查阅 Session 管理章节
- **THEN** 可以看到 FTS5 搜索、Session 分裂等功能的对比

### Requirement: 架构对比文档应包含工具系统分析
对比文档 SHALL 包含工具系统的对比，包括：
- 注册机制
- 并发安全分类
- MCP 支持
- 内置工具列表

#### Scenario: 用户了解工具系统差异
- **WHEN** 用户查阅工具系统章节
- **THEN** 可以看到两个仓库的工具注册、并发处理的对比

### Requirement: 架构对比文档应包含 Skills 系统分析
对比文档 SHALL 包含 Skills 技能系统的对比，包括：
- 加载机制
- 技能库规模
- 技能自改进机制

#### Scenario: 用户了解 Skills 系统差异
- **WHEN** 用户查阅 Skills 系统章节
- **THEN** 可以看到技能数量、自改进机制的对比

### Requirement: 架构对比文档应包含 Gateway/消息平台分析
对比文档 SHALL 包含消息网关平台的对比，包括：
- 支持的平台列表
- 适配器设计模式
- 路由机制

#### Scenario: 用户了解平台支持差异
- **WHEN** 用户查阅 Gateway 章节
- **THEN** 可以看到两个仓库支持的平台数量和适配方式对比

### Requirement: 架构对比文档应包含权限与安全分析
对比文档 SHALL 包含权限安全系统的对比，包括：
- 权限控制模式
- 审批机制
- 钩子执行

#### Scenario: 用户了解权限系统差异
- **WHEN** 用户查阅权限安全章节
- **THEN** 可以看到 PermissionMode、审批回调的对比

### Requirement: 架构对比文档应包含记忆系统分析
对比文档 SHALL 包含记忆系统的对比，包括：
- 记忆持久化方式
- 用户建模
- 自我 nudges 机制

#### Scenario: 用户了解记忆系统差异
- **WHEN** 用户查阅记忆系统章节
- **THEN** 可以看到 MemoryType、Honcho 集成的对比

### Requirement: 架构对比文档应提供借鉴建议
对比文档 SHALL 包含可借鉴功能的优先级建议，包括：
- 高价值低风险功能
- 需要基础设施的功能
- 架构变动大的功能

#### Scenario: 用户获取演进建议
- **WHEN** 用户查阅借鉴建议章节
- **THEN** 可以看到按优先级排序的功能借鉴建议