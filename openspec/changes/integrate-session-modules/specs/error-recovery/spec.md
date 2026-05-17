## ADDED Requirements

### Requirement: Error classification on LLM call failure

The system SHALL classify errors into ErrorKind categories: NETWORK, TIMEOUT, RATE_LIMIT, AUTH, PROMPT_TOO_LONG, MAX_OUTPUT_TOKENS, HTTP, UNKNOWN.

#### Scenario: Network error classification
- **WHEN** error message contains "connection" or "network"
- **THEN** system classifies as ErrorKind.NETWORK

#### Scenario: Rate limit error classification
- **WHEN** error message contains "rate limit" or HTTP code 429
- **THEN** system classifies as ErrorKind.RATE_LIMIT

#### Scenario: Prompt too long error classification
- **WHEN** error message contains "prompt_too_long" or "context_length_exceeded"
- **THEN** system classifies as ErrorKind.PROMPT_TOO_LONG

### Requirement: Retry with exponential backoff

The system SHALL retry failed LLM calls based on error classification with exponential backoff delay.

#### Scenario: Network error retry
- **WHEN** ErrorKind.NETWORK with max_retries=3, base_delay=2.0
- **THEN** system retries up to 3 times with delays: 2s, 4s, 8s (capped at max_delay=30s)

#### Scenario: Rate limit retry
- **WHEN** ErrorKind.RATE_LIMIT with max_retries=5, base_delay=10.0
- **THEN** system retries up to 5 times with delays: 10s, 20s, 40s (capped at 30s)

#### Scenario: Auth error - no retry
- **WHEN** ErrorKind.AUTH
- **THEN** system does not retry and returns formatted error message immediately

### Requirement: Circuit breaker protection

The system SHALL implement circuit breaker that opens after consecutive_failures >= max_failures (3) and closes after cooldown_seconds (60).

#### Scenario: Circuit breaker opens
- **WHEN** consecutive_failures >= 3
- **THEN** circuit breaker opens and rejects new requests for 60 seconds

#### Scenario: Circuit breaker closes after cooldown
- **WHEN** cooldown period (60s) has passed since last failure
- **THEN** circuit breaker closes and allows new requests

#### Scenario: Circuit breaker resets on success
- **WHEN** a successful LLM call completes
- **THEN** consecutive_failures resets to 0

### Requirement: Prompt too long recovery via compaction

The system SHALL recover from PROMPT_TOO_LONG errors by invoking compaction callback to reduce message history.

#### Scenario: Compaction recovery triggered
- **WHEN** ErrorKind.PROMPT_TOO_LONG and compaction_callback is set
- **THEN** system invokes compaction callback to reduce messages and retries

#### Scenario: No compaction callback available
- **WHEN** ErrorKind.PROMPT_TOO_LONG and compaction_callback is not set
- **THEN** system returns error message without retry

### Requirement: User-facing error messages

The system SHALL format errors into user-friendly messages in the user's language.

#### Scenario: Rate limit message
- **WHEN** ErrorKind.RATE_LIMIT
- **THEN** system returns "API请求频率超限。请稍后重试。" with error details

#### Scenario: Timeout message
- **WHEN** ErrorKind.TIMEOUT
- **THEN** system returns "请求超时。任务可能过于复杂，建议拆分。" with error details