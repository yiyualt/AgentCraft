# Feature: Tool Calling & MCP

## 背景

本地 LLM（如 Qwen3）支持 OpenAI-compatible Function Calling。我们需要一个框架来：
1. 注册工具（Tool Registry）
2. LLM 请求工具时执行
3. 将结果送回 LLM
4. 支持 MCP (Model Context Protocol) 标准

## 目标

- [ ] Tool Registry：声明式注册 Python 函数为 LLM 可调用的 Tool
- [ ] Tool Execution Loop：LLM → Tool Call → 执行 → 结果送回 LLM → 最终回答
- [ ] MCP Stdio 支持：通过 `npx` 启动外部 MCP server 并调用其工具
- [ ] 内置工具：时间、计算、文件读写、Web 搜索

## 设计

```python
@tool(
    name="get_weather",
    description="查询指定城市的天气",
    parameters={
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "城市名称"}
        },
        "required": ["city"]
    }
)
def get_weather(city: str) -> dict:
    """实际的 Python 实现"""
    ...
```

## Tool Execution Loop

```
1. User: "北京天气怎么样？"
2. LLM: tool_call → get_weather(city="北京")
3. Gateway: 执行 get_weather("北京") → {"temperature": 22, ...}
4. Gateway: 把结果作为 tool message 送回 LLM
5. LLM: "北京目前 22°C，天气晴朗"
6. Gateway: 最终回答返回给用户
```
