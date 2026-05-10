# Tech Stack — AgentCraft

## 当前栈 (Phase 1 完成)

| 组件 | 技术 | 说明 |
|------|------|------|
| LLM Runtime | Ollama | 本地模型推理 |
| LLM API | OpenAI-compatible | `http://127.0.0.1:8000/v1` |
| Python Runtime | CPython 3.13+ | uv 管理依赖 |
| Gateway | FastAPI | 请求代理 + MLflow 追踪 |
| Observability | MLflow | 实验追踪、日志、指标 |
| Tool Calling | 自建 ToolRegistry + MCP stdio | 本地工具 + 外部 MCP server |
| Client SDK | openai Python | 调用 LLM API |

## 后续可能引入 (按阶段)

| 组件 | 候选技术 | 考虑因素 |
|------|----------|----------|
| Agent Framework | 自建 (不依赖 LangChain) | 学习目的，轻量 |
| Session Store | SQLite (裸 sqlite3，不用 ORM) | 零依赖，足够个人使用 |
| Skills Registry | 文件系统 + frontmatter 解析 | 轻量，无需数据库 |
| Message Queue | 内置 asyncio Queue | 个人场景不需要 Kafka |
| Channel Adapters | httpx + WebSocket | Telegram Bot API / Slack SDK |
| Container | Docker | 可选，未来沙箱用 |
| Frontend / Canvas | 待定 | 阶段 5 再决定 |

## 原则

- **延迟决策**: 不到需要的时候不引入新依赖
- **偏好标准协议**: OpenAI API / MCP 协议 / SSE — 优先选择标准化接口
- **可替换**: 每个组件都应该能在不重写整个系统的情况下替换
