# Prompt Cache Sharing - Fork Agent Cache Optimization

## Overview

Prompt Cache Sharing允许fork的子agent共享父agent对话的prompt cache prefix，显著降低API成本。Claude Code通过实验验证：无cache共享时98% cache miss，共享后接近全命中。

## Goals

| Goal | Status | Description |
|------|--------|-------------|
| Cache前缀识别 | ❌ | 识别可缓存的对话前缀部分 |
| Fork Cache共享 | ❌ | Fork子agent复用父对话cache |
| Cache命中统计 | ❌ | 记录cache hit/miss率 |
| 成本优化验证 | ❌ | 验证成本降低效果 |

## Current State

当前Fork机制（sessions/fork.py）：

```python
def create_fork_context(parent_session_id: str, max_tokens: int = 32000) -> ForkContext:
    parent_messages = session_manager.get_messages_openai(parent_session_id)
    
    # 截断超过限制的消息
    if token_count > max_tokens:
        parent_messages = sliding_window_truncate(parent_messages)
    
    # 添加placeholder
    parent_messages.append({"role": "user", "content": FORK_PLACEHOLDER})
    
    return ForkContext(
        parent_session_id=parent_session_id,
        inherited_messages=parent_messages,
    )
```

**问题**：
- 每个fork child发送独立请求，无法复用父对话的cache
- DeepSeek API支持prompt cache（Beta），但当前实现未利用
- 相同前缀重复付费，成本浪费

## Target State

实现Prompt Cache Sharing后：

```
父对话: [system, msg1, msg2, msg3, ..., assistant(tool_calls)]
        ↑ Cache Prefix (共享部分)

Fork Child 1: [Cache Prefix, user("task 1")]  → cache命中
Fork Child 2: [Cache Prefix, user("task 2")]  → cache命中
Fork Child 3: [Cache Prefix, user("task 3")]  → cache命中
```

**效果**：
- 所有fork children共享相同的cache prefix
- 只有最后一个user message不同（task描述）
- Cache命中率接近100%，成本大幅降低

## Technical Design

### 1. DeepSeek Prompt Cache机制

DeepSeek API支持prompt caching（Beta特性）：

```python
# DeepSeek API请求参数
response = await client.chat.completions.create(
    model="deepseek-chat",
    messages=messages,
    # 自动缓存：system prompt + 前面多个message blocks
    # 当后续请求有相同前缀时，cache命中
)
```

**Cache规则**：
- System prompt 自动缓存
- 消息块（连续的user/assistant对）可缓存
- Cache有效期：约5分钟（API侧管理）
- Cache命中时，`usage.cache_read_input_tokens` > 0

### 2. Fork Placeholder固定化

当前实现中，placeholder在build_fork_messages时替换：

```python
# 当前：每个fork child的placeholder被替换为不同task
Fork Child 1: [..., user("分析代码结构")]
Fork Child 2: [..., user("写单元测试")]
```

这导致前缀不同 → cache无法命中。

**改进方案**：保持placeholder位置固定，在LLM响应后注入task：

```python
# 改进：placeholder保持固定
Fork Child 1: [..., user(FORK_PLACEHOLDER)]
# LLM收到placeholder，在第一轮响应时注入task
# 或：在system prompt中注入task，保持messages前缀一致
```

### 3. Cache Prefix设计

```python
class CachePrefixManager:
    """管理可缓存的对话前缀"""
    
    def __init__(self, session_manager: SessionManager):
        self._session_manager = session_manager
        self._cache_prefixes: dict[str, CachePrefix] = {}
    
    def create_cache_prefix(
        self,
        session_id: str,
        max_cached_tokens: int = 32000,
    ) -> CachePrefix:
        """创建可缓存的对话前缀"""
        messages = self._session_manager.get_messages_openai(session_id)
        
        # 计算token，截断到max_cached_tokens
        calculator = TokenCalculator()
        truncated = self._truncate_to_limit(messages, max_cached_tokens, calculator)
        
        # 添加固定的placeholder结尾
        truncated.append({
            "role": "user",
            "content": FORK_PLACEHOLDER,
            "cache_control": {"type": "ephemeral"},  # Anthropic style
        })
        
        prefix = CachePrefix(
            session_id=session_id,
            messages=truncated,
            token_count=calculator.count_messages(truncated),
        )
        
        self._cache_prefixes[session_id] = prefix
        return prefix
    
    def build_fork_request(
        self,
        cache_prefix: CachePrefix,
        task: str,
    ) -> list[dict]:
        """构建fork请求，复用cache prefix"""
        # 复制prefix messages
        messages = cache_prefix.messages.copy()
        
        # 方案1：替换placeholder（前缀相同，最后一条不同）
        # DeepSeek会缓存除最后一条外的所有消息
        for i, msg in enumerate(messages):
            if msg.get("content") == FORK_PLACEHOLDER:
                messages[i] = {"role": "user", "content": task}
        
        # 方案2（更优）：在system prompt注入task
        # messages前缀完全相同 → cache全命中
        # system_msg = messages[0]
        # system_msg["content"] += f"\n\n<fork_task>{task}</fork_task>"
        
        return messages
```

### 4. Cache命中统计

```python
@dataclass
class CacheStats:
    """Prompt cache统计"""
    
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_cached_tokens: int = 0
    total_new_tokens: int = 0
    estimated_cost_saved: float = 0.0
    
    def hit_rate(self) -> float:
        return self.cache_hits / self.total_requests if self.total_requests > 0 else 0.0
    
    def cost_saved_percentage(self) -> float:
        # DeepSeek: cached tokens cost 0.1x of new tokens
        if self.total_new_tokens + self.total_cached_tokens == 0:
            return 0.0
        full_cost = (self.total_cached_tokens + self.total_new_tokens) * COST_PER_TOKEN
        actual_cost = self.total_cached_tokens * 0.1 * COST_PER_TOKEN + self.total_new_tokens * COST_PER_TOKEN
        return (full_cost - actual_cost) / full_cost * 100

class CacheStatsTracker:
    """追踪cache统计"""
    
    def record_usage(self, usage: dict):
        """记录一次API调用的cache使用"""
        cached = usage.get("cache_read_input_tokens", 0)
        new = usage.get("prompt_tokens", 0) - cached
        
        self._stats.total_requests += 1
        if cached > 0:
            self._stats.cache_hits += 1
            self._stats.total_cached_tokens += cached
        else:
            self._stats.cache_misses += 1
        
        self._stats.total_new_tokens += new
        self._stats.estimated_cost_saved += cached * COST_PER_TOKEN * 0.9
```

### 5. Gateway集成

```python
# gateway.py 修改
class GatewayState:
    _cache_prefix_manager: CachePrefixManager = None
    _cache_stats: CacheStatsTracker = None

async def lifespan(app: FastAPI):
    # 初始化cache manager
    state._cache_prefix_manager = CachePrefixManager(_session_manager)
    state._cache_stats = CacheStatsTracker()
    yield

# 在Agent tool调用时
async def agent_delegate(prompt: str, fork_from_current: bool = False):
    if fork_from_current:
        session_id = get_current_session_id()
        
        # 创建/获取cache prefix
        cache_prefix = state._cache_prefix_manager.get_or_create(session_id)
        
        # 构建fork请求
        messages = state._cache_prefix_manager.build_fork_request(cache_prefix, prompt)
        
        # 执行fork agent
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
        )
        
        # 记录cache使用
        state._cache_stats.record_usage(response.usage)
        
        return response.content
```

## Implementation Plan

### Phase 1: Cache Prefix基础
1. 创建 `CachePrefixManager` 类 — sessions/cache_prefix.py
2. 实现 `create_cache_prefix()` 前缀创建 — sessions/cache_prefix.py
3. 实现 `build_fork_request()` 请求构建 — sessions/cache_prefix.py
4. 实现 FORK_PLACEHOLDER 固定机制

### Phase 2: Fork集成
1. 修改 `ForkManager` 使用 CachePrefixManager
2. 实现fork请求cache复用
3. 测试cache命中情况

### Phase 3: 统计追踪
1. 创建 `CacheStatsTracker` 类 — sessions/cache_stats.py
2. 在gateway中记录cache使用
3. 实现 `/cache-stats` API端点查看统计

### Phase 4: 成本验证
1. 设计对比实验（无cache vs 有cache）
2. 测量实际成本降低
3. 优化cache prefix长度

## API Changes

### 新增Cache统计端点

```python
@app.get("/cache-stats")
async def get_cache_stats():
    """获取prompt cache统计"""
    return {
        "total_requests": stats.total_requests,
        "hit_rate": stats.hit_rate(),
        "total_cached_tokens": stats.total_cached_tokens,
        "estimated_cost_saved_usd": stats.estimated_cost_saved,
        "cost_saved_percentage": stats.cost_saved_percentage(),
    }
```

### Fork请求格式

```python
# Fork请求示例
{
    "messages": [
        {"role": "system", "content": "...", "cache_control": {"type": "ephemeral"}},
        {"role": "user", "content": "previous context..."},
        {"role": "assistant", "content": "response..."},
        # ... 更多历史消息（cache prefix）
        {"role": "user", "content": "[FORK_TASK_PLACEHOLDER]"},  # 固定placeholder
    ]
}

# 实际发送时替换最后一条
{"role": "user", "content": "分析代码结构"}
```

## Success Criteria

- [ ] CachePrefixManager可创建可缓存前缀
- [ ] Fork请求复用父对话cache prefix
- [ ] Cache命中率统计准确
- [ ] 实际测量：成本降低 > 50%
- [ ] 统计API返回准确数据

## Cost Analysis

**假设场景**：父对话10k tokens，fork 5个子任务

**无Cache Sharing**：
```
每个fork发送完整10k + task tokens
总tokens: 5 × (10k + 0.5k) = 52.5k
成本: 52.5k × $0.14/1M ≈ $0.00735
```

**有Cache Sharing**：
```
每个fork复用10k cache + 新增0.5k task tokens
Cached tokens: 5 × 10k = 50k (成本 0.1x)
New tokens: 5 × 0.5k = 2.5k
成本: 50k × 0.1 × $0.14/1M + 2.5k × $0.14/1M ≈ $0.00105
节省: 85%
```

**Claude Code实验数据**（Anthropic）：
- 无cache共享：98% cache miss
- 有cache共享：接近100% cache hit
- 成本降低：约90%