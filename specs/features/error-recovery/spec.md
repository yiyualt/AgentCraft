# Error Recovery - Multi-layer Resilience

## Overview

多层错误恢复系统处理各种API和执行错误，确保agent能从失败中恢复而不是直接崩溃。通过错误分类、重试策略、恢复机制提高系统稳定性。

## Goals

| Goal | Status | Description |
|------|--------|-------------|
| 错误分类 | ❌ | 分类错误类型（网络、超时、认证、限流等） |
| 重试策略 | ❌ | 不同错误类型采用不同重试策略 |
| Prompt恢复 | ❌ | prompt_too_long错误触发compaction后重试 |
| 输出恢复 | ❌ | max_output_tokens错误自动继续 |
| 优雅降级 | ❌ | 不可恢复错误返回友好提示 |

## Current State

当前系统只有简单timeout和try-catch：
```python
try:
    result = await asyncio.wait_for(..., timeout=timeout)
except asyncio.TimeoutError:
    return f"Task timed out after {timeout}s"
```

**问题**：
- 网络错误直接失败
- API限流无法处理
- prompt_too_long无法恢复
- 没有重试机制

## Target State

实现错误恢复后：
```
错误发生 → 分类 → 选择策略
策略:
  - 网络错误 → 重试（指数退避）
  - 超时 → 重试或返回部分结果
  - 限流 → 等待后重试
  - prompt_too_long → compaction后重试
  - max_output_tokens → 继续生成
  - 认证错误 → 直接失败（提示检查配置）
```

## Technical Design

### 1. 错误分类

```python
from enum import Enum

class ErrorKind(Enum):
    NETWORK = "network"       # 网络连接失败
    TIMEOUT = "timeout"       # 请求超时
    RATE_LIMIT = "rate_limit" # API限流
    AUTH = "auth"             # 认证失败
    PROMPT_TOO_LONG = "prompt_too_long"  # 输入超长
    MAX_OUTPUT_TOKENS = "max_output_tokens"  # 输出超限
    HTTP = "http"             # HTTP错误（4xx/5xx）
    UNKNOWN = "unknown"       # 未知错误

def classify_error(error: Exception) -> ErrorKind:
    """分类错误类型"""
    error_str = str(error).lower()

    if "timeout" in error_str or "timed out" in error_str:
        return ErrorKind.TIMEOUT

    if "rate limit" in error_str or "429" in error_str:
        return ErrorKind.RATE_LIMIT

    if "auth" in error_str or "401" in error_str or "403" in error_str:
        return ErrorKind.AUTH

    if "prompt_too_long" in error_str or "context_length_exceeded" in error_str:
        return ErrorKind.PROMPT_TOO_LONG

    if "max_output_tokens" in error_str or "length" in error_str:
        return ErrorKind.MAX_OUTPUT_TOKENS

    if "connection" in error_str or "network" in error_str:
        return ErrorKind.NETWORK

    if any(code in error_str for code in ["400", "404", "500", "502", "503"]):
        return ErrorKind.HTTP

    return ErrorKind.UNKNOWN
```

### 2. 重试策略

```python
class RetryStrategy:
    max_retries: int = 3
    base_delay: float = 1.0  # 秒
    max_delay: float = 30.0  # 秒
    exponential_base: float = 2.0

def get_retry_config(error_kind: ErrorKind) -> RetryStrategy:
    """根据错误类型获取重试配置"""
    configs = {
        ErrorKind.NETWORK: RetryStrategy(max_retries=3, base_delay=2.0),
        ErrorKind.TIMEOUT: RetryStrategy(max_retries=2, base_delay=5.0),
        ErrorKind.RATE_LIMIT: RetryStrategy(max_retries=5, base_delay=10.0),
        ErrorKind.HTTP: RetryStrategy(max_retries=2, base_delay=3.0),
        ErrorKind.PROMPT_TOO_LONG: RetryStrategy(max_retries=1, base_delay=0),  # 先compaction
        ErrorKind.MAX_OUTPUT_TOKENS: RetryStrategy(max_retries=1, base_delay=0),  # 继续
        ErrorKind.AUTH: RetryStrategy(max_retries=0),  # 不重试
        ErrorKind.UNKNOWN: RetryStrategy(max_retries=1, base_delay=1.0),
    }
    return configs.get(error_kind, RetryStrategy(max_retries=0))

def calculate_delay(attempt: int, strategy: RetryStrategy) -> float:
    """计算重试延迟（指数退避）"""
    delay = strategy.base_delay * (strategy.exponential_base ** attempt)
    return min(delay, strategy.max_delay)
```

### 3. 恢复机制

**A. Prompt Too Long恢复**
```python
async def handle_prompt_too_long(
    messages: list,
    compact_state: AutoCompactState,
) -> tuple[list, bool]:
    """
    处理prompt_too_long错误

    Returns:
        (compact_messages, success)
    """
    if compact_state.consecutive_failures >= 3:
        return messages, False  # 熔断

    # 触发reactive compact
    compact_messages = await do_reactive_compact(messages)
    compact_state.consecutive_failures += 1

    return compact_messages, True
```

**B. Max Output Tokens恢复**
```python
async def handle_max_output_tokens(
    messages: list,
    partial_response: dict,
) -> tuple[list, str]:
    """
    处理max_output_tokens错误

    继续生成，注入partial response
    """
    # 添加partial response到消息
    messages.append(partial_response["choices"][0]["message"])

    # 添加继续提示
    messages.append({
        "role": "user",
        "content": "Continue generating from where you stopped."
    })

    # 再次调用LLM
    continuation = await call_llm(messages)
    return messages, partial_content + continuation
```

### 4. 执行包装器

```python
class ResilientExecutor:
    """带错误恢复的执行器"""

    def __init__(self, agent_executor: AgentExecutor):
        self._executor = agent_executor
        self._compact_state = AutoCompactState()

    async def run_with_recovery(
        self,
        messages: list,
        tools: list,
        max_turns: int,
    ) -> str:
        """带恢复的执行循环"""
        retry_count = 0

        while True:
            try:
                return await self._executor._run_loop(messages, tools, max_turns)

            except Exception as e:
                error_kind = classify_error(e)
                strategy = get_retry_config(error_kind)

                # 认证错误不重试
                if error_kind == ErrorKind.AUTH:
                    return f"[Error] Authentication failed. Check your API configuration."

                # 超过最大重试次数
                if retry_count >= strategy.max_retries:
                    return f"[Error] {error_kind.value}: {str(e)}. Max retries exceeded."

                # Prompt太长 → 先压缩
                if error_kind == ErrorKind.PROMPT_TOO_LONG:
                    messages, success = await handle_prompt_too_long(
                        messages, self._compact_state
                    )
                    if not success:
                        return "[Error] Context too long, compaction failed."
                    retry_count = 0  # 重置计数
                    continue

                # 输出超限 → 继续
                if error_kind == ErrorKind.MAX_OUTPUT_TOKENS:
                    # 特殊处理：继续生成
                    ...

                # 其他错误 → 等待后重试
                delay = calculate_delay(retry_count, strategy)
                logger.warning(f"Error {error_kind.value}, retrying in {delay}s...")
                await asyncio.sleep(delay)
                retry_count += 1
```

### 5. 降级策略

不可恢复时返回友好提示：
```python
ERROR_MESSAGES = {
    ErrorKind.AUTH: "认证失败。请检查API密钥配置。",
    ErrorKind.RATE_LIMIT: "API请求频率超限。请稍后重试。",
    ErrorKind.NETWORK: "网络连接失败。请检查网络设置。",
    ErrorKind.PROMPT_TOO_LONG: "对话历史过长。请尝试新对话或手动清理。",
    ErrorKind.TIMEOUT: "请求超时。任务可能过于复杂，建议拆分。",
}

def format_error_message(error_kind: ErrorKind, detail: str) -> str:
    """格式化错误消息"""
    base_msg = ERROR_MESSAGES.get(error_kind, "未知错误")
    return f"[Error] {base_msg}\n详情: {detail}"
```

## Implementation Plan

### Phase 1: 错误分类
1. 实现 `ErrorKind` 分类枚举
2. 实现 `classify_error()` 函数
3. 测试各种错误类型识别

### Phase 2: 重试策略
1. 实现 `RetryStrategy` 配置
2. 实现指数退避延迟计算
3. 实现重试循环

### Phase 3: 特殊恢复
1. 实现 prompt_too_long → compaction恢复
2. 实现 max_output_tokens → 继续生成
3. 实现熔断机制

### Phase 4: 包装器
1. 实现 `ResilientExecutor` 类
2. 集成到 `AgentExecutor`
3. 测试各种错误场景

## Success Criteria

- [ ] 错误分类准确
- [ ] 网络错误重试成功
- [ ] 限流错误等待后重试
- [ ] prompt_too_long触发compaction
- [ ] max_output_tokens能继续生成
- [ ] 认证错误直接返回友好提示
- [ ] 连续失败3次后熔断