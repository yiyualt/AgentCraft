## MODIFIED Requirements

### Requirement: add_message 支持记忆触发
SessionManager.add_message() SHALL 在存储消息后检查是否触发记忆提取。

原有逻辑：
- 存消息到 messages 表
- 更新 session 的 message_count 和 token_count
- 返回 Message 对象

新增逻辑：
- 如果 role=user，增加 batch_count
- 如果 batch_count >= 5，触发 MemoryExtractor.analyze_and_save() 并清零

#### Scenario: user 消息触发计数
- **WHEN** add_message(role="user") 被调用
- **THEN** 系统 SHALL 增加 session.message_count_batch
- **AND** 如果 batch_count >= 5，触发记忆检查并清零

#### Scenario: 非 user 消息不计数
- **WHEN** add_message(role="assistant") 或 add_message(role="tool") 被调用
- **THEN** 系统 SHALL 不增加 batch_count
- **AND** 不触发记忆检查

#### Scenario: 触发后清零
- **WHEN** batch_count 达到 5 并触发记忆检查
- **THEN** 系统 SHALL 将 batch_count 清零
- **AND** 下一个 user 消息从 batch_count=1 开始计数