# Plan: Live Canvas

## Step 1: 最小 Web 工作台

**涉及文件**: `canvas/server.py` + `static/canvas.html` (新建)

- 简单的 Web 页面，显示 Agent 的"工作台"
- Agent 通过 tool call (`canvas_update`) 更新工作台内容
- 工作台通过 SSE 实时获取更新

## Step 2: Canvas Tool

**涉及文件**: `tools/builtin.py` (新增工具)

```
@tool(name="canvas_update", description="更新工作台内容")
def canvas_update(content: str, mode: str = "markdown") -> str:
    # 将内容推送到 Canvas
```

- mode: markdown / code / table / html
- 内容通过 asyncio.Queue 推送到 SSE 客户端

## Step 3: 交互式组件

**涉及文件**: `canvas/interactive.py` (新建)

- 支持表单、按钮等交互组件
- 用户交互事件回传给 Agent

## Step 4: A2UI 协议

**涉及文件**: `canvas/a2ui.py` (新建)

- Agent-to-User Interface 协议
- JSON Schema 描述 UI 组件
- 类似 MCP 的标准化方式

## 依赖

- 无新依赖（FastAPI SSE 已有）
- Phase 6 再引入复杂前端框架