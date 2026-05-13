# Streaming Tool Execution - Parallel Tool Processing

## Overview

Streaming Tool Execution允许在API响应还在流式传输时就启动工具执行，而不是等待完整响应后才开始。这是Claude Code最大的性能优势，显著减少等待时间。

## Goals

| Goal | Status | Description |
|------|--------|-------------|
| 流式工具解析 | ✅ | 在API streaming时解析tool_use块 |
| 并行工具执行 | ✅ | isConcurrencySafe工具并行执行（最多10个） |
| 错误级联取消 | ✅ | BashTool错误取消兄弟进程 |
| 进度实时反馈 | ✅ | SSE返回工具执行进度（tool_start/tool_result事件） |

## Implementation

**新增文件**：
- `streaming_executor.py` — StreamingToolExecutor核心类

**修改文件**：
- `gateway.py` — 集成StreamingToolExecutor，添加SSE streaming支持

当前gateway.py的工具执行流程：

```python
# gateway.py _handle_non_streaming()
while True:
    response = await client.chat.completions.create(...)  # 等待完整响应
    message = response.choices[0].message
    
    if not message.tool_calls:
        break  # 没有工具调用，结束
    
    # 顺序执行所有工具
    for tool_call in message.tool_calls:
        result = await registry.dispatch(tool_call.function.name, ...)
        messages.append({"role": "tool", "content": result, ...})
```

**问题**：
- 必须等待完整API响应才能开始工具执行
- 工具顺序执行，无并行能力
- 长响应时间 = API响应时间 + Σ工具执行时间
- BashTool失败无法取消其他正在执行的工具

## Target State

实现Streaming Tool Execution后：

```
API开始streaming → 解析tool_use块 → 立即启动工具执行
                              ↓
            [Tool1执行] [Tool2执行] [Tool3执行]  (并行)
                              ↓
            API响应完成 → 所有工具结果ready → 返回给API
```

**效果**：
- 响应时间 ≈ max(API响应时间, 工具执行时间)
- 并行工具执行节省大量时间
- 错误可级联取消兄弟工具

## Technical Design

### 1. StreamingToolExecutor架构

```python
class StreamingToolExecutor:
    """在API streaming时并行执行工具"""
    
    def __init__(self, registry: UnifiedToolRegistry, max_concurrency: int = 10):
        self._registry = registry
        self._max_concurrency = max_concurrency
        self._pending_tools: dict[str, asyncio.Task] = {}
        self._abort_controller: asyncio.Task = None
    
    async def on_tool_use_block(self, tool_call_id: str, tool_name: str, arguments: dict):
        """收到tool_use块时立即启动执行"""
        if self._is_concurrency_safe(tool_name):
            # 可并行工具：立即启动
            task = asyncio.create_task(
                self._execute_tool_safe(tool_call_id, tool_name, arguments)
            )
            self._pending_tools[tool_call_id] = task
        else:
            # 非安全工具：排队等待
            await self._queue_tool(tool_call_id, tool_name, arguments)
    
    async def get_results(self) -> dict[str, ToolResult]:
        """等待所有工具完成，返回结果"""
        results = {}
        for tool_call_id, task in self._pending_tools.items():
            try:
                results[tool_call_id] = await task
            except Exception as e:
                results[tool_call_id] = ToolResult(error=str(e))
        return results
    
    def cancel_all(self, reason: str = "sibling_error"):
        """取消所有正在执行的工具（级联取消）"""
        for task in self._pending_tools.values():
            task.cancel(reason)
```

### 2. 工具并发安全分类

```python
# 工具并发安全标记
CONCURRENCY_SAFE_TOOLS = {
    # 只读工具 - 可安全并行
    "Read", "Glob", "Grep", "WebFetch", "WebSearch",
    # 无状态工具 - 可安全并行
    "CountTokens",
}

CONCURRENCY_UNSAFE_TOOLS = {
    # 文件修改 - 需串行执行防止冲突
    "Write", "Edit",
    # Shell执行 - 需串行执行防止竞态
    "Bash",
    # Agent调用 - 需串行执行防止递归
    "Agent", "Skill",
}

def is_concurrency_safe(tool_name: str) -> bool:
    """判断工具是否可并行执行"""
    return tool_name in CONCURRENCY_SAFE_TOOLS
```

### 3. 流式解析与执行集成

```python
# gateway.py 修改
async def _handle_streaming_with_tool_execution(
    messages: list,
    tools: list,
    session_id: str,
):
    """流式响应 + 工具并行执行"""
    
    executor = StreamingToolExecutor(_registry)
    assistant_message = {"role": "assistant", "content": "", "tool_calls": []}
    
    # 创建streaming请求
    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,
        stream=True,
    )
    
    # 处理streaming事件
    for event in stream:
        delta = event.choices[0].delta
        
        if delta.content:
            assistant_message["content"] += delta.content
            yield {"type": "content", "text": delta.content}
        
        if delta.tool_calls:
            for tc in delta.tool_calls:
                # 解析到完整的tool_use块
                if tc.function.name and tc.function.arguments:
                    # 立即启动工具执行
                    await executor.on_tool_use_block(
                        tc.id,
                        tc.function.name,
                        json.loads(tc.function.arguments)
                    )
                    assistant_message["tool_calls"].append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    })
    
    # 等待所有工具完成
    results = await executor.get_results()
    
    # 构建tool消息
    for tool_call_id, result in results.items():
        if result.error:
            yield {"type": "tool_error", "id": tool_call_id, "error": result.error}
        else:
            yield {"type": "tool_result", "id": tool_call_id, "result": result.content}
        
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result.error or result.content,
        })
```

### 4. 错误级联取消

```python
class BashToolExecutor:
    """Bash工具特殊处理 - 错误级联取消"""
    
    def __init__(self, executor: StreamingToolExecutor):
        self._executor = executor
        self._sibling_abort_controller = asyncio.Event()
    
    async def execute(self, command: str, timeout: int = 60):
        """执行Bash命令，失败时取消所有兄弟工具"""
        try:
            result = await run_bash_command(command, timeout)
            return ToolResult(content=result)
        except Exception as e:
            # BashTool失败 → 取消所有正在执行的兄弟工具
            self._executor.cancel_all(reason=f"bash_error: {e}")
            raise
```

### 5. 进度反馈系统

```python
class ToolProgressReporter:
    """工具执行进度实时反馈"""
    
    async def report_start(self, tool_call_id: str, tool_name: str):
        """工具开始执行"""
        yield {
            "type": "tool_start",
            "id": tool_call_id,
            "name": tool_name,
            "timestamp": time.time(),
        }
    
    async def report_progress(self, tool_call_id: str, progress: str):
        """工具执行进度"""
        yield {
            "type": "tool_progress",
            "id": tool_call_id,
            "progress": progress,
        }
    
    async def report_complete(self, tool_call_id: str, result: str):
        """工具完成"""
        yield {
            "type": "tool_complete",
            "id": tool_call_id,
            "result": result[:500],  # 截断防止过长
        }
```

## API Changes

### Gateway Streaming响应格式

```python
# 新的streaming事件格式
{
    "type": "content",        # 文本内容
    "text": "...",
}
{
    "type": "tool_start",     # 工具开始
    "id": "call_xxx",
    "name": "Read",
}
{
    "type": "tool_progress",  # 工具进度（可选）
    "id": "call_xxx",
    "progress": "Reading file...",
}
{
    "type": "tool_result",    # 工具结果
    "id": "call_xxx",
    "result": "...",
}
{
    "type": "tool_error",     # 工具错误
    "id": "call_xxx",
    "error": "...",
}
```

### HTTP SSE响应

```
# /v1/chat/completions SSE格式
event: content
data: {"text": "I'll read the file..."}

event: tool_start
data: {"id": "call_123", "name": "Read"}

event: tool_result
data: {"id": "call_123", "result": "file contents..."}
```

## Implementation Plan

### Phase 1: StreamingToolExecutor基础
1. 创建 `StreamingToolExecutor` 类 — gateway/streaming_executor.py
2. 实现 `is_concurrency_safe()` 工具分类 — gateway/streaming_executor.py
3. 实现 `on_tool_use_block()` 立即执行 — gateway/streaming_executor.py
4. 实现 `get_results()` 结果收集 — gateway/streaming_executor.py

### Phase 2: 流式解析集成
1. 修改 gateway.py 支持 streaming + tool execution
2. 实现 tool_use 块流式解析
3. 集成 StreamingToolExecutor
4. 实现进度反馈 SSE

### Phase 3: 并行执行与级联取消
1. 实现并发控制（max_concurrency=10）
2. 实现 BashTool 错误级联取消
3. 实现工具排队（非安全工具串行）
4. 测试并行执行性能

### Phase 4: 前端集成（可选）
1. UI显示工具执行进度
2. 实时更新工具状态
3. 错误可视化

## Integration Points

### gateway.py修改

```python
# 当前: Request-Response模式
@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    return await _handle_non_streaming(...)

# 目标: Streaming模式
@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    if request.stream:
        return StreamingResponse(
            _handle_streaming_with_tool_execution(...),
            media_type="text/event-stream",
        )
    else:
        return await _handle_non_streaming(...)
```

### Tool装饰器扩展

```python
# tools/__init__.py
@tool(
    name="Read",
    description="...",
    concurrency_safe=True,  # 新参数：标记并发安全
)
def read_file(file_path: str) -> str:
    ...

@tool(
    name="Bash",
    description="...",
    concurrency_safe=False,  # 默认False
    cascades_on_error=True,  # 新参数：错误级联取消
)
def run_bash(command: str) -> str:
    ...
```

## Success Criteria

- [ ] StreamingToolExecutor可立即启动工具执行
- [ ] 并发安全工具可并行执行（最多10个）
- [ ] BashTool错误级联取消兄弟工具
- [ ] SSE实时返回工具执行进度
- [ ] 性能提升：响应时间接近max(API时间, 工具时间)
- [ ] 非安全工具正确排队串行执行

## Performance Comparison

**当前模式**：
```
API响应: 2s
工具执行: Read(0.5s) + Grep(1s) + Bash(3s) = 4.5s
总时间: 2s + 4.5s = 6.5s
```

**目标模式**：
```
API响应: 2s (同时工具执行)
工具执行: max(Read(0.5s), Grep(1s))并行 + Bash(3s)串行 = 3s
总时间: max(2s, 3s) = 3s
节省: 53%
```