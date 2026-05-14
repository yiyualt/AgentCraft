## ADDED Requirements

### Requirement: Agent Control Plane abstraction

The system SHALL provide an AgentControlPlane for multi-agent collaboration.

#### Scenario: ACP initialization
- **WHEN** ACP is created
- **THEN** it has unique ID, empty children list, and result queue

#### Scenario: Spawn child agent
- **WHEN** parent calls `spawn_child(task, context)`
- **THEN** child agent is created with inherited context and registered to parent

#### Scenario: Child agent limit
- **WHEN** spawning child agents
- **THEN** maximum number is enforced (default: 10), excess spawns raise error

### Requirement: Parent Stream for result aggregation

The system SHALL provide parent stream to receive child agent results in real-time.

#### Scenario: Stream iteration
- **WHEN** parent iterates `parent_stream()`
- **THEN** each child result is yielded as it completes

#### Scenario: Stream termination
- **WHEN** all child agents complete
- **THEN** parent stream ends (no more yields)

#### Scenario: Stream timeout
- **WHEN** parent stream waits longer than timeout (default: 300s)
- **THEN** stream yields timeout error for remaining children

### Requirement: Parent-child communication

The system SHALL support parent sending messages to child agents.

#### Scenario: Direct message to child
- **WHEN** parent calls `send_to_child(child_id, message)`
- **THEN** message is received by specific child agent

#### Scenario: Broadcast to all children
- **WHEN** parent calls `broadcast(message)`
- **THEN** message is received by all active child agents

#### Scenario: Child receives message
- **WHEN** child agent has pending message from parent
- **THEN** message is available in child's inbox for processing

### Requirement: Context inheritance

The system SHALL support child agents inheriting partial parent context.

#### Scenario: Inherit messages
- **WHEN** child is spawned with `inherited_context`
- **THEN** child's initial messages include parent's recent messages (limited by token budget)

#### Scenario: Inherit tools
- **WHEN** child is spawned
- **THEN** child has access to subset of parent's tools (Agent tool disabled to prevent recursion)

#### Scenario: Context size limit
- **WHEN** inherited context exceeds limit (default: 32000 tokens)
- **THEN** context is truncated (keep system + recent messages)

### Requirement: Child agent execution

The system SHALL execute child agents independently with result reporting.

#### Scenario: Child execution
- **WHEN** child agent runs
- **THEN** it executes task using inherited context + assigned task

#### Scenario: Result reporting
- **WHEN** child completes execution
- **THEN** result is put to parent's result queue

#### Scenario: Error handling
- **WHEN** child execution fails
- **THEN** error is reported to parent as ChildResult with error field