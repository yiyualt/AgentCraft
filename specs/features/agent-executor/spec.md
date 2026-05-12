# Feature: Agent Executor (Sub-agent Delegation)

## 背景

复杂任务往往需要分解为多个子任务，每个子任务可能需要不同的工具集和专注的上下文。Agent Executor 提供子代理委托能力，让主 Agent 可以将子任务委托给专门的子代理处理。

## 目标

- [x] 三种专门代理类型：explore、general-purpose、plan
- [x] 子代理独立上下文，不继承主对话历史
- [x] 工具集可限定（如 explore 只能使用 Glob、Grep、Read）
- [x] 超时控制，防止子代理无限运行
- [x] 轮次限制，防止工具循环过多

## 代理类型

### explore
- **用途**: 快速只读搜索，定位代码文件、符号、关键词
- **工具**: Glob, Grep, Read, WebFetch
- **轮次**: 最多 5 轮
- **特点**: 不用于代码审查、开放分析

### general-purpose
- **用途**: 复杂问题研究、多步骤任务执行
- **工具**: 全部可用
- **轮次**: 最多 10 轮
- **特点**: 通用型，适合不确定搜索结果的场景

### plan
- **用途**: 设计实现方案、架构规划
- **工具**: Glob, Grep, Read, Write
- **轮次**: 最多 8 轮
- **特点**: 输出步骤计划、识别关键文件、权衡方案

## 接口

```python
class AgentExecutor:
    async def run(
        task: str,
        agent_type: str = "general-purpose",
        context: str | None = None,
        timeout: int = 120,
    ) -> str
```

## 使用示例

```
1. 主 Agent 收到用户请求："分析这个项目的数据库连接模块"
2. 主 Agent 调用 Agent 工具，subagent_type="explore"，prompt="找出所有数据库连接相关文件"
3. explore 子代理使用 Glob/Grep 搜索，返回文件列表
4. 主 Agent 继续处理，基于子代理结果进行深入分析
```

## 实现

### Agent 工具 (`tools/builtin.py`)

```python
@tool(name="Agent", description="Launch a new agent...")
async def agent_delegate(prompt: str, description: str | None = None, subagent_type: str = "general-purpose") -> str:
    executor = get_agent_executor()
    result = await executor.run(task=prompt, agent_type=subagent_type, timeout=120)
    return result
```

### AgentExecutor (`tools/agent_executor.py`)

- 构建 System Prompt，注入代理类型描述
- 筛选可用工具列表
- 运行 Tool Execution Loop
- 返回最终结果或超时/轮次限制提示

## 配置

无需额外配置，使用主 Gateway 的 LLM Client 和 Tool Registry。

## 验证

```bash
# 测试子代理委托
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"用 explore agent 找出所有 Python 测试文件"}]}'
```