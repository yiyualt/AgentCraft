#!/usr/bin/env python3
"""Unit tests for Error Recovery system."""

import asyncio
import time
import pytest
from sessions.error_recovery import (
    ErrorKind,
    RetryStrategy,
    CircuitState,
    ResilientExecutor,
    classify_error,
    get_retry_config,
    calculate_delay,
    format_error_message,
    ERROR_MESSAGES,
    RETRY_CONFIGS,
)


# ============================================================
# ErrorKind & Classification
# ============================================================

class TestClassifyError:
    def test_timeout_in_message(self):
        assert classify_error(Exception("Request timed out")) == ErrorKind.TIMEOUT
        assert classify_error(Exception("timed out after 30s")) == ErrorKind.TIMEOUT

    def test_rate_limit_429(self):
        assert classify_error(Exception("Rate limit exceeded. 429")) == ErrorKind.RATE_LIMIT
        assert classify_error(Exception("HTTP 429 Too Many Requests")) == ErrorKind.RATE_LIMIT

    def test_auth_401_403(self):
        assert classify_error(Exception("Authentication failed: 401")) == ErrorKind.AUTH
        assert classify_error(Exception("HTTP 403 Forbidden")) == ErrorKind.AUTH
        assert classify_error(Exception("auth error")) == ErrorKind.AUTH

    def test_prompt_too_long(self):
        assert classify_error(Exception("prompt_too_long error")) == ErrorKind.PROMPT_TOO_LONG
        assert classify_error(Exception("context_length_exceeded")) == ErrorKind.PROMPT_TOO_LONG

    def test_max_output_tokens(self):
        assert classify_error(Exception("max_output_tokens exceeded")) == ErrorKind.MAX_OUTPUT_TOKENS

    def test_network_error(self):
        assert classify_error(Exception("Connection refused")) == ErrorKind.NETWORK
        assert classify_error(Exception("Network is unreachable")) == ErrorKind.NETWORK

    def test_http_status_codes(self):
        assert classify_error(Exception("Server error: 500")) == ErrorKind.HTTP
        assert classify_error(Exception("Bad gateway: 502")) == ErrorKind.HTTP
        assert classify_error(Exception("Service unavailable: 503")) == ErrorKind.HTTP
        assert classify_error(Exception("Not found: 404")) == ErrorKind.HTTP
        assert classify_error(Exception("Bad request: 400")) == ErrorKind.HTTP

    def test_unknown_error(self):
        assert classify_error(Exception("Something unexpected happened")) == ErrorKind.UNKNOWN


# ============================================================
# Retry Strategy
# ============================================================

class TestRetryStrategy:
    def test_defaults(self):
        s = RetryStrategy()
        assert s.max_retries == 3
        assert s.base_delay == 1.0
        assert s.max_delay == 30.0
        assert s.exponential_base == 2.0

    def test_custom(self):
        s = RetryStrategy(max_retries=5, base_delay=2.0, max_delay=60.0, exponential_base=3.0)
        assert s.max_retries == 5
        assert s.base_delay == 2.0


class TestGetRetryConfig:
    def test_all_error_kinds_have_config(self):
        for kind in ErrorKind:
            cfg = get_retry_config(kind)
            assert isinstance(cfg, RetryStrategy)

    def test_auth_has_zero_retries(self):
        cfg = get_retry_config(ErrorKind.AUTH)
        assert cfg.max_retries == 0

    def test_rate_limit_has_most_retries(self):
        cfg = get_retry_config(ErrorKind.RATE_LIMIT)
        assert cfg.max_retries == 5
        assert cfg.base_delay == 10.0

    def test_prompt_too_long_single_retry(self):
        cfg = get_retry_config(ErrorKind.PROMPT_TOO_LONG)
        assert cfg.max_retries == 1


class TestCalculateDelay:
    def test_first_attempt(self):
        delay = calculate_delay(0, RetryStrategy(base_delay=2.0, exponential_base=2.0))
        assert delay == 2.0  # 2.0 * 2.0^0

    def test_second_attempt(self):
        delay = calculate_delay(1, RetryStrategy(base_delay=2.0, exponential_base=2.0))
        assert delay == 4.0  # 2.0 * 2.0^1

    def test_third_attempt(self):
        delay = calculate_delay(2, RetryStrategy(base_delay=2.0, exponential_base=2.0))
        assert delay == 8.0  # 2.0 * 2.0^2

    def test_capped_at_max_delay(self):
        s = RetryStrategy(base_delay=10.0, max_delay=30.0, exponential_base=2.0)
        delay = calculate_delay(3, s)  # 10 * 2^3 = 80, capped at 30
        assert delay == 30.0


# ============================================================
# Circuit Breaker
# ============================================================

class TestCircuitState:
    def test_initially_closed(self):
        c = CircuitState()
        assert not c.is_open()

    def test_opens_after_max_failures(self):
        c = CircuitState(max_failures=3)
        c.record_failure()
        c.record_failure()
        c.record_failure()
        assert c.is_open()

    def test_not_open_below_max(self):
        c = CircuitState(max_failures=3)
        c.record_failure()
        c.record_failure()
        assert not c.is_open()

    def test_cooldown_resets(self):
        c = CircuitState(max_failures=3, cooldown_seconds=0)
        c.record_failure()
        c.record_failure()
        c.record_failure()
        # Cooldown of 0 means time.time() - last_failure_time > 0, so it resets
        assert not c.is_open()

    def test_stays_open_within_cooldown(self):
        c = CircuitState(max_failures=3, cooldown_seconds=3600)
        c.record_failure()
        c.record_failure()
        c.record_failure()
        assert c.is_open()  # Very long cooldown, can't have reset

    def test_record_success_resets(self):
        c = CircuitState(max_failures=3)
        c.record_failure()
        c.record_failure()
        c.record_failure()
        c.record_success()
        assert c.consecutive_failures == 0
        assert not c.is_open()


# ============================================================
# ResilientExecutor
# ============================================================

class TestResilientExecutor:
    @pytest.mark.asyncio
    async def test_success_no_recovery_needed(self):
        executor = ResilientExecutor()
        call_count = 0

        async def llm_call():
            nonlocal call_count
            call_count += 1
            return "success_result"

        result, msgs = await executor.run_with_recovery(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            max_turns=1,
            llm_call=llm_call,
        )
        assert result == "success_result"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_network_error(self):
        executor = ResilientExecutor(max_total_retries=5)
        call_count = 0

        async def flaky_call():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Connection refused")
            return "success"

        result, msgs = await executor.run_with_recovery(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            max_turns=1,
            llm_call=flaky_call,
        )
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_auth_error_fails_immediately(self):
        executor = ResilientExecutor()
        call_count = 0

        async def auth_fail():
            nonlocal call_count
            call_count += 1
            raise Exception("HTTP 401 Unauthorized")

        result, msgs = await executor.run_with_recovery(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            max_turns=1,
            llm_call=auth_fail,
        )
        assert "Authentication" in result or "认证" in result
        assert call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        executor = ResilientExecutor(max_total_retries=2)

        async def always_fail():
            raise Exception("Network error: connection refused")

        result, msgs = await executor.run_with_recovery(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            max_turns=1,
            llm_call=always_fail,
        )
        assert "超过最大重试次数" in result or "Max retries" in result

    @pytest.mark.asyncio
    async def test_prompt_too_long_triggers_compaction(self):
        executor = ResilientExecutor()
        compacted = []

        async def compaction_callback(msgs):
            compacted.append(len(msgs))
            return msgs[:3]  # Return trimmed version

        executor.set_compaction_callback(compaction_callback)

        call_count = 0
        long_msgs = [{"role": "user", "content": "x" * 1000} for _ in range(10)]

        async def prompt_long_call():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("prompt_too_long: context_length_exceeded")
            return "success_after_compact"

        result, msgs = await executor.run_with_recovery(
            messages=long_msgs,
            tools=[],
            max_turns=1,
            llm_call=prompt_long_call,
        )
        assert result == "success_after_compact"
        assert len(compacted) == 1
        assert compacted[0] == 10

    @pytest.mark.asyncio
    async def test_timeout_caught_via_asyncio(self):
        executor = ResilientExecutor(max_total_retries=2)
        call_count = 0

        async def timeout_call():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError()
            return "success"

        result, msgs = await executor.run_with_recovery(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            max_turns=1,
            llm_call=timeout_call,
        )
        assert result == "success"
        assert call_count == 2


# ============================================================
# Format Error Messages
# ============================================================

class TestFormatError:
    def test_auth_message(self):
        msg = format_error_message(ErrorKind.AUTH, "Invalid API key")
        assert "认证" in msg
        assert "Invalid API key" in msg

    def test_network_message(self):
        msg = format_error_message(ErrorKind.NETWORK, "DNS resolution failed")
        assert "网络" in msg

    def test_all_error_kinds_have_messages(self):
        for kind in ErrorKind:
            assert kind in ERROR_MESSAGES
            assert ERROR_MESSAGES[kind]


# ============================================================
# All strategies configured
# ============================================================

class TestAllConfigsPresent:
    def test_all_error_kinds_in_retry_configs(self):
        for kind in ErrorKind:
            assert kind in RETRY_CONFIGS, f"Missing retry config for {kind}"
