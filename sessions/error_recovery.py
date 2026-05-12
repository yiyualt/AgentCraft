"""Multi-layer error recovery with classification, retry, and graceful degradation.

Classifies errors, applies per-type retry strategies with exponential backoff,
handles prompt_too_long via compaction, and provides circuit breaker protection.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("gateway")


# ============================================================
# Error Classification
# ============================================================

class ErrorKind(Enum):
    NETWORK = "network"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    PROMPT_TOO_LONG = "prompt_too_long"
    MAX_OUTPUT_TOKENS = "max_output_tokens"
    HTTP = "http"
    UNKNOWN = "unknown"


def classify_error(error: Exception) -> ErrorKind:
    """Classify an exception into an error kind for retry strategy selection."""
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
    if any(code in error_str for code in ("400", "404", "500", "502", "503")):
        return ErrorKind.HTTP
    return ErrorKind.UNKNOWN


# ============================================================
# Retry Strategy
# ============================================================

@dataclass
class RetryStrategy:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0


RETRY_CONFIGS: dict[ErrorKind, RetryStrategy] = {
    ErrorKind.NETWORK:         RetryStrategy(max_retries=3, base_delay=2.0),
    ErrorKind.TIMEOUT:         RetryStrategy(max_retries=2, base_delay=5.0),
    ErrorKind.RATE_LIMIT:      RetryStrategy(max_retries=5, base_delay=10.0),
    ErrorKind.HTTP:            RetryStrategy(max_retries=2, base_delay=3.0),
    ErrorKind.PROMPT_TOO_LONG:  RetryStrategy(max_retries=1, base_delay=0),
    ErrorKind.MAX_OUTPUT_TOKENS: RetryStrategy(max_retries=1, base_delay=0),
    ErrorKind.AUTH:            RetryStrategy(max_retries=0),
    ErrorKind.UNKNOWN:         RetryStrategy(max_retries=1, base_delay=1.0),
}


def get_retry_config(error_kind: ErrorKind) -> RetryStrategy:
    return RETRY_CONFIGS.get(error_kind, RetryStrategy(max_retries=0))


def calculate_delay(attempt: int, strategy: RetryStrategy) -> float:
    delay = strategy.base_delay * (strategy.exponential_base ** attempt)
    return min(delay, strategy.max_delay)


# ============================================================
# User-facing error messages
# ============================================================

ERROR_MESSAGES: dict[ErrorKind, str] = {
    ErrorKind.AUTH: "认证失败。请检查API密钥配置。",
    ErrorKind.RATE_LIMIT: "API请求频率超限。请稍后重试。",
    ErrorKind.NETWORK: "网络连接失败。请检查网络设置。",
    ErrorKind.PROMPT_TOO_LONG: "对话历史过长。请尝试新对话或手动清理。",
    ErrorKind.MAX_OUTPUT_TOKENS: "输出超限。任务需要拆分。",
    ErrorKind.TIMEOUT: "请求超时。任务可能过于复杂，建议拆分。",
    ErrorKind.HTTP: "服务端错误。请稍后重试。",
    ErrorKind.UNKNOWN: "未知错误。",
}


def format_error_message(error_kind: ErrorKind, detail: str) -> str:
    base_msg = ERROR_MESSAGES.get(error_kind, "未知错误")
    return f"[Error] {base_msg}\n详情: {detail}"


# ============================================================
# Circuit Breaker State
# ============================================================

@dataclass
class CircuitState:
    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    max_failures: int = 3
    cooldown_seconds: int = 60

    def is_open(self) -> bool:
        if self.consecutive_failures < self.max_failures:
            return False
        if time.time() - self.last_failure_time >= self.cooldown_seconds:
            self.consecutive_failures = 0
            return False
        return True

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        self.last_failure_time = time.time()

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.last_failure_time = 0.0


# ============================================================
# Resilient Executor
# ============================================================

class ResilientExecutor:
    """Wraps LLM calls with retry, circuit breaker, and recovery logic."""

    def __init__(
        self,
        max_total_retries: int = 5,
        circuit_max_failures: int = 3,
        circuit_cooldown_seconds: int = 60,
    ):
        self._max_total_retries = max_total_retries
        self._circuit = CircuitState(
            max_failures=circuit_max_failures,
            cooldown_seconds=circuit_cooldown_seconds,
        )
        self._compaction_callback: Callable | None = None

    def set_compaction_callback(self, callback: Callable) -> None:
        """Register a callback for prompt_too_long compaction.

        The callback receives (messages: list) -> list (compacted messages).
        """
        self._compaction_callback = callback

    async def run_with_recovery(
        self,
        messages: list[dict],
        tools: list[dict],
        max_turns: int,
        llm_call: Callable,
        *,
        session_id: str = "",
    ) -> tuple[str, list[dict]]:
        """Execute LLM loop with error recovery.

        Returns (result_string, final_messages).
        """
        total_retries = 0
        local_messages = messages

        while True:
            # Circuit breaker check
            if self._circuit.is_open():
                logger.error("[RECOVERY] Circuit breaker open, aborting")
                return (
                    "[Error] 连续失败次数过多，已进入保护状态。请稍后重试。",
                    local_messages,
                )

            try:
                result = await llm_call()
                self._circuit.record_success()
                return result, local_messages

            except asyncio.TimeoutError:
                error = Exception("Request timed out")
                error_kind = ErrorKind.TIMEOUT

            except Exception as e:
                error = e
                error_kind = classify_error(e)

            strategy = get_retry_config(error_kind)

            # Auth errors — no retry
            if error_kind == ErrorKind.AUTH:
                logger.error("[RECOVERY] Auth error, not retrying")
                self._circuit.record_failure()
                return format_error_message(error_kind, str(error)), local_messages

            # Prompt too long → compaction recovery
            if error_kind == ErrorKind.PROMPT_TOO_LONG:
                logger.warning("[RECOVERY] Prompt too long, attempting compaction...")
                if self._compaction_callback:
                    local_messages = await self._compaction_callback(local_messages)
                    logger.info(f"[RECOVERY] Compacted to {len(local_messages)} messages, retrying")
                else:
                    self._circuit.record_failure()
                    return format_error_message(error_kind, str(error)), local_messages
                total_retries += 1
                continue

            # Max output tokens → continue generating (sub-agent context)
            if error_kind == ErrorKind.MAX_OUTPUT_TOKENS:
                logger.warning("[RECOVERY] Max output tokens reached, continuing generation")
                # The stop reason is handled naturally — continue the loop
                total_retries += 1
                continue

            # Check global retry budget
            if total_retries >= self._max_total_retries:
                logger.error(f"[RECOVERY] Total retries exhausted: {total_retries}")
                self._circuit.record_failure()
                return (
                    f"[Error] 超过最大重试次数。原因: {error_kind.value} - {str(error)[:200]}",
                    local_messages,
                )

            # Per-kind retry limit
            if total_retries >= strategy.max_retries:
                logger.error(
                    f"[RECOVERY] Max retries ({strategy.max_retries}) exceeded for {error_kind.value}"
                )
                self._circuit.record_failure()
                return format_error_message(error_kind, str(error)), local_messages

            # Wait and retry
            delay = calculate_delay(total_retries, strategy)
            logger.warning(
                f"[RECOVERY] {error_kind.value}: {str(error)[:100]}. "
                f"Retrying in {delay:.1f}s (attempt {total_retries + 1}/{strategy.max_retries})"
            )
            await asyncio.sleep(delay)
            total_retries += 1

    def reset_circuit(self) -> None:
        self._circuit.record_success()


# ============================================================
# Public API
# ============================================================

__all__ = [
    "ErrorKind",
    "RetryStrategy",
    "CircuitState",
    "ResilientExecutor",
    "classify_error",
    "get_retry_config",
    "calculate_delay",
    "format_error_message",
    "ERROR_MESSAGES",
    "RETRY_CONFIGS",
]
