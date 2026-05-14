# ACP (Agent Control Plane) 使用指南

## 概述

ACP是AgentCraft的多Agent协作系统，允许主Agent派发子Agent并行执行任务。

## 核心概念

```
主Agent (Parent)
    │
    │ spawn_child(task)
    │
    ├── 子Agent A: 执行任务1
    ├── 子Agent B: 执行任务2
    ├── 子Agent C: 执行任务3
    │
    │ wait_all() 或 parent_stream()
    │
    ▼
收集结果，汇总回复
```

## API端点

### 1. 派发子Agent

```http
POST /acp/spawn
Content-Type: application/json

{
    "task": "查看README.md内容",
    "agent_type": "explore",
    "timeout": 180
}
```

**响应:**
```json
{
    "child_id": "child-abc123",
    "task": "查看README.md内容",
    "agent_type": "explore",
    "state": "idle",
    "started_at": 1715689000.5
}
```

### 2. 查看ACP状态

```http
GET /acp/status
```

**响应:**
```json
{
    "total_spawned": 3,
    "active": 2,
    "completed": 1,
    "failed": 0,
    "max_children": 10,
    "children": {
        "child-abc123": {
            "task": "查看README.md内容",
            "state": "completed",
            "elapsed": 5.2
        },
        ...
    }
}
```

### 3. 等待所有子Agent完成

```http
POST /acp/wait
Content-Type: application/json

{
    "timeout": 120
}
```

**响应:**
```json
{
    "child-abc123": "README.md内容摘要...",
    "child-def456": "gateway.py有650行...",
    "child-ghi789": "tools目录有10个文件..."
}
```

### 4. 广播消息

```http
POST /acp/broadcast
Content-Type: application/json

{
    "message": "加快进度"
}
```

## Agent类型

| 类型 | 描述 | 最大轮次 | 可用工具 |
|------|------|---------|---------|
| `explore` | 快速搜索Agent | 5 | Glob, Grep, Read, WebFetch |
| `general-purpose` | 通用Agent | 10 | 所有工具 |
| `plan` | 架构设计Agent | 8 | Glob, Grep, Read, Write |

## 约束和限制

### 1. 子Agent数量限制
- 默认最多10个子Agent同时运行
- 超过限制时返回400错误

### 2. 超时控制
- 默认180秒
- 可在spawn时指定自定义超时

### 3. 递归保护
- 子Agent不能再spawn新的子Agent
- Agent tool在子Agent中被禁用

### 4. 上下文继承限制
- 继承父对话上下文，但限制32000 tokens
- 超出时自动裁剪（保留system + 最近消息）

## 使用示例

### Python客户端

```python
import httpx

client = httpx.AsyncClient(base_url="http://localhost:8000")

# 派发子Agent
response = await client.post("/acp/spawn", json={
    "task": "分析项目结构",
    "agent_type": "explore",
})
child_id = response.json()["child_id"]

# 等待完成
results = await client.post("/acp/wait", json={"timeout": 120})
print(results.json())
```

### 并行执行多个任务

```python
# 派发多个子Agent
tasks = [
    ("分析安全性", "explore"),
    ("写测试", "general-purpose"),
    ("整理文档", "plan"),
]

for task, agent_type in tasks:
    await client.post("/acp/spawn", json={
        "task": task,
        "agent_type": agent_type,
    })

# 等待所有完成
results = await client.post("/acp/wait", json={"timeout": 180})
```

## 最佳实践

### 1. 选择合适的Agent类型
- 搜索代码用 `explore`
- 复杂任务用 `general-purpose`
- 设计方案用 `plan`

### 2. 设置合理的超时
- 简单搜索: 60秒
- 中等任务: 120秒
- 复杂任务: 180秒

### 3. 避免过度并行
- 3-5个子Agent通常足够
- 过多子Agent会增加资源消耗

### 4. 监控状态
- 使用 `/acp/status` 检查进度
- 及时处理失败的子Agent

### 5. 任务拆分
- 每个子Agent任务应该清晰独立
- 避免任务之间有依赖关系