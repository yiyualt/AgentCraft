# Feature: Tool Calling & MCP

## 背景

本地 LLM（如 Qwen3）支持 OpenAI-compatible Function Calling。我们需要一个框架来：
1. 注册工具（Tool Registry）
2. LLM 请求工具时执行
3. 将结果送回 LLM
4. 支持 MCP (Model Context Protocol) 标准

## 目标

- [x] Tool Registry：声明式注册 Python 函数为 LLM 可调用的 Tool
- [x] Tool Execution Loop：LLM → Tool Call → 执行 → 结果送回 LLM → 最终回答
- [x] MCP Stdio 支持：通过 `npx`/`uvx` 启动外部 MCP server 并调用其工具
- [x] 内置工具：时间、计算、文件读写、Web 搜索

## 实现

### 本地工具 (`tools/__init__.py`)

```python
@tool(
    name="calculator",
    description="Evaluate math expressions",
    parameters={...}
)
def calculator(expression: str) -> str:
    return str(eval(expression, ...))
```

### MCP 工具 (`tools/mcp/`)

```python
# 配置文件 mcp_config.json
{
  "mcpServers": {
    "git": {
      "command": "uvx",
      "args": ["mcp-server-git"],
      "enabled": true
    }
  }
}

# Gateway 启动时自动加载 MCP servers
# 工具名格式: server.tool_name (如 git.git_log)
```

## Tool Execution Loop

```
1. User: "最近3条commit记录？"
2. LLM: tool_call → git.git_log(repo_path=".", max_count=3)
3. Gateway: 通过 MCP stdio 调用 git server → commit history
4. Gateway: 结果作为 tool message 送回 LLM
5. LLM: "以下是最近3条提交记录..."
6. Gateway: 最终回答返回给用户
```

## 验证

```bash
# 测试 MCP 工具调用
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"查看git log"}]}'
```
