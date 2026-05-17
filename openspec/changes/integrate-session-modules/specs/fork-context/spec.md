## ADDED Requirements

### Requirement: Fork context creation for sub-agent

The system SHALL create ForkContext when Agent tool spawns a child agent, inheriting parent conversation history up to max_tokens (32000 default).

#### Scenario: Fork context created successfully
- **WHEN** Agent tool requests fork context with parent_session_id
- **THEN** system returns ForkContext with inherited_messages truncated to max_tokens and placeholder at end

#### Scenario: Parent session not found
- **WHEN** parent_session_id does not exist
- **THEN** system returns None and logs warning

#### Scenario: Parent has no messages
- **WHEN** parent session exists but has no messages
- **THEN** system returns None and logs warning

### Requirement: Orphan tool messages cleanup

The system SHALL clean orphan tool messages (tool messages without preceding assistant tool_calls) before creating fork context.

#### Scenario: Orphan tool message removed
- **WHEN** a tool message exists without preceding assistant message with tool_calls
- **THEN** system removes that tool message from inherited messages

#### Scenario: Matching tool message kept
- **WHEN** a tool message has tool_call_id matching preceding assistant's tool_calls
- **THEN** system keeps that tool message in inherited messages

### Requirement: Placeholder replacement with task

The system SHALL replace FORK_PLACEHOLDER with actual task string when building fork messages.

#### Scenario: Placeholder replaced
- **WHEN** fork_manager.build_fork_messages(fork_context, task) is called
- **THEN** FORK_PLACEHOLDER token is replaced with actual task content

### Requirement: Fork child detection for recursion protection

The system SHALL detect if current context is a fork child to prevent recursive agent spawning.

#### Scenario: Fork child detected
- **WHEN** messages contain system message with "<fork>" content OR user message with FORK_PLACEHOLDER
- **THEN** system returns True for is_in_fork_child()

#### Scenario: Not a fork child
- **WHEN** messages do not contain fork markers
- **THEN** system returns False for is_in_fork_child()

### Requirement: Fork child boilerplate injection

The system SHALL inject FORK_CHILD_BOILERPLATE as system message for forked agents, containing execution constraints.

#### Scenario: Boilerplate injected
- **WHEN** fork context is created
- **THEN** system adds fork_system_msg with FORK_CHILD_BOILERPLATE as first message in inherited_messages

### Requirement: Sliding window truncation for context limit

The system SHALL apply sliding window truncation when inherited context exceeds max_tokens limit.

#### Scenario: Context exceeds limit
- **WHEN** parent messages token count > max_tokens (32000)
- **THEN** system applies SlidingWindowStrategy.truncate_messages() to reduce to limit