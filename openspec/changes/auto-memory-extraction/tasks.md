## 1. 数据模型扩展

- [x] 1.1 在 Session 表增加 message_count_batch 字段（INTEGER, DEFAULT 0）
- [x] 1.2 在 sessions/models.py 的 Session dataclass 增加 message_count_batch 属性
- [x] 1.3 在 SCHEMA 中增加 message_count_batch 列的迁移逻辑
- [x] 1.4 在 SessionManager._row_to_session() 中解析 message_count_batch

## 2. MemoryExtractor 模块创建

- [x] 2.1 创建 sessions/memory_extractor.py 文件
- [x] 2.2 定义 MemoryExtractor 类（接受 llm_client 参数）
- [x] 2.3 实现 analyze_and_save(session_id, messages) 方法
- [x] 2.4 实现 _keyword_filter(messages) 方法（关键词检测）
- [x] 2.5 定义关键词列表（中文和英文）
- [x] 2.6 实现 _llm_analyze(messages) 方法（调用 LLM 判断）
- [x] 2.7 实现 _infer_type(content) 方法（复用 memory_tools._infer_memory_type）
- [x] 2.8 实现 _save_memory(content, type) 方法（调用 memory_tools.remember）

## 3. SessionManager 触发逻辑

- [x] 3.1 在 add_message() 中增加 role == "user" 判断
- [x] 3.2 增加 batch_count +1 逻辑（更新 session.message_count_batch）
- [x] 3.3 增加 batch_count >= 5 判断
- [x] 3.4 触发时调用 get_messages(session_id, limit=20)
- [x] 3.5 触发时 asyncio.create_task(memory_extractor.analyze_and_save())
- [x] 3.6 触发后清零 batch_count
- [x] 3.7 返回 tuple (Message, should_trigger) 供 app.py 使用

## 4. app.py 集成

- [x] 4.1 在 startup 时初始化 MemoryExtractor（传入 llm_client）
- [x] 4.2 在 add_message 后检查 should_trigger 并触发记忆提取

## 5. 测试验证

- [ ] 5.1 测试计数逻辑（5 个 user 消息触发）
- [ ] 5.2 测试计数清零（触发后从 1 开始）
- [ ] 5.3 测试非 user 消息不计数
- [ ] 5.4 测试关键词检测（包含关键词时触发 LLM）
- [ ] 5.5 测试 LLM 分析（判断值得记录的内容）
- [ ] 5.6 测试记忆保存（调用 remember 成功）
- [ ] 5.7 测试后台执行（不阻塞 add_message）