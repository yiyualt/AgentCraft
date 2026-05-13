## ADDED Requirements

### Requirement: CLI entry point supports one-shot execution

The system SHALL provide a CLI entry point that executes a single task and exits.

#### Scenario: One-shot task execution
- **WHEN** user runs `agentcraft "分析代码结构"`
- **THEN** system executes the task with LLM and tool execution
- **THEN** system prints the result to stdout
- **THEN** system exits with code 0

#### Scenario: One-shot with model selection
- **WHEN** user runs `agentcraft "分析代码结构" --model deepseek-chat`
- **THEN** system uses the specified model for LLM calls

### Requirement: CLI supports interactive REPL mode

The system SHALL provide an interactive REPL mode for continuous conversation.

#### Scenario: Interactive mode entry
- **WHEN** user runs `agentcraft --interactive`
- **THEN** system enters REPL mode with prompt
- **THEN** user can input messages continuously

#### Scenario: Interactive mode exit
- **WHEN** user types `/exit` or Ctrl-D in REPL mode
- **THEN** system exits cleanly

### Requirement: CLI displays tool execution progress

The system SHALL display real-time tool execution progress during task execution.

#### Scenario: Tool start notification
- **WHEN** tool execution begins
- **THEN** system displays "[Tool: Read] executing..."
- **THEN** system shows progress indicator

#### Scenario: Tool result display
- **WHEN** tool execution completes
- **THEN** system displays result summary
- **THEN** result is truncated if longer than 200 characters

### Requirement: CLI supports slash commands

The system SHALL support slash commands for configuration during interactive mode.

#### Scenario: Goal command
- **WHEN** user types `/goal tests pass` in REPL
- **THEN** system sets goal condition for session

#### Scenario: Permission command
- **WHEN** user types `/permission bypass` in REPL
- **THEN** system sets permission mode to bypass

### Requirement: CLI supports streaming LLM output

The system SHALL display LLM responses in streaming fashion, character by character.

#### Scenario: Streaming output display
- **WHEN** LLM generates response tokens
- **THEN** system prints each token immediately
- **THEN** no blocking until complete response

### Requirement: CLI supports session persistence

The system SHALL optionally persist session history to file for later retrieval.

#### Scenario: Session persistence with name
- **WHEN** user runs `agentcraft -i --session dev-session`
- **THEN** system saves conversation history to ~/.agentcraft/sessions/dev-session.jsonl

#### Scenario: Session restoration
- **WHEN** user runs `agentcraft -i --session dev-session` again
- **THEN** system loads previous conversation history