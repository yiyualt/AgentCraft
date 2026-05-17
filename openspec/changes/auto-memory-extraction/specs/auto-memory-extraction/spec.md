## ADDED Requirements

### Requirement: 自动触发记忆检查
系统 SHALL 在每 5 个 user 消息后自动触发记忆检查。

#### Scenario: 达到触发条件
- **WHEN** SessionManager.add_message() 收到第 5 个 role=user 的消息
- **THEN** 系统 SHALL 触发 MemoryExtractor.analyze_and_save()
- **AND** 计数器 SHALL 清零

#### Scenario: 未达到触发条件
- **WHEN** SessionManager.add_message() 收到第 1-4 个 role=user 的消息
- **THEN** 系统 SHALL 只增加计数器
- **AND** 不触发记忆检查

#### Scenario: 非 user 消息不计数
- **WHEN** SessionManager.add_message() 收到 role=assistant 或 role=tool 的消息
- **THEN** 系统 SHALL 不增加计数器
- **AND** 不触发记忆检查

### Requirement: 检查最近消息内容
系统 SHALL 检查最近 20 条消息（包含所有角色）。

#### Scenario: 获取最近消息
- **WHEN** 记忆检查被触发
- **THEN** 系统 SHALL 获取 session 的最近 20 条消息
- **AND** 消息 SHALL 包含 user + assistant + tool 角色

#### Scenario: 后台异步执行
- **WHEN** 记忆检查被触发
- **THEN** 系统 SHALL 使用 asyncio.create_task() 后台执行
- **AND** 不阻塞 SessionManager.add_message() 的响应

### Requirement: 智能判断值得记录的内容
系统 SHALL 使用关键词检测 + LLM 分析判断是否值得记录。

#### Scenario: 关键词检测触发
- **WHEN** 消息内容包含关键词（"记住", "请记住", "不要", "always", "never" 等）
- **THEN** 系统 SHALL 调用 LLM 进行深度分析
- **AND** LLM SHALL 判断内容是否值得记录

#### Scenario: LLM 判断有价值
- **WHEN** LLM 判断内容有价值（用户偏好、项目约束等）
- **THEN** 系统 SHALL 调用 memory_tools.remember() 保存记忆
- **AND** 自动推断记忆类型（user/feedback/project/reference）

#### Scenario: 无关键词不触发 LLM
- **WHEN** 消息内容不包含关键词
- **THEN** 系统 SHALL 不调用 LLM
- **AND** 不保存记忆（节省成本）

### Requirement: 自动保存记忆
系统 SHALL 后台调用 memory_tools.remember() 保存记忆。

#### Scenario: 成功保存记忆
- **WHEN** LLM 判断内容值得记录
- **THEN** 系统 SHALL 调用 remember(content, type=inferred_type)
- **AND** 记忆 SHALL 保存到 memory.db

#### Scenario: 保存失败不影响主流程
- **WHEN** remember() 调用失败（如 API 错误）
- **THEN** 系统 SHALL 记录错误日志
- **AND** 不影响用户对话继续进行