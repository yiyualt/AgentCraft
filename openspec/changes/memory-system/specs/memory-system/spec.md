## ADDED Requirements

### Requirement: Memory types supported

The system SHALL support four memory types: user, feedback, project, and reference.

#### Scenario: Create user memory
- **WHEN** user says "remember that I'm a senior Go engineer"
- **THEN** system creates a memory entry with type=user containing this information

#### Scenario: Create feedback memory
- **WHEN** user says "don't mock the database in tests"
- **THEN** system creates a memory entry with type=feedback with rule and reason

#### Scenario: Create project memory
- **WHEN** LLM detects project context like "auth middleware rewrite is for compliance"
- **THEN** system creates a memory entry with type=project with fact and motivation

### Requirement: Memory file format

The system SHALL store memories as Markdown files with YAML frontmatter in `~/.agentcraft/projects/<project-hash>/memory/`.

#### Scenario: Memory file structure
- **WHEN** a memory is saved
- **THEN** file contains YAML frontmatter (name, description, type, created_at) followed by Markdown content

#### Scenario: Memory file naming
- **WHEN** memory name is "user-role"
- **THEN** file is saved as `user-role.md`

### Requirement: Memory index file

The system SHALL maintain `MEMORY.md` as an index file listing all memories with brief descriptions.

#### Scenario: Index file format
- **WHEN** multiple memories exist
- **THEN** MEMORY.md contains list of `- [Title](file.md) — one-line hook` entries

#### Scenario: Index file truncation
- **WHEN** MEMORY.md exceeds 200 lines
- **THEN** older entries are truncated to fit limit

### Requirement: Memory loading at session start

The system SHALL load MEMORY.md into conversation context at session startup without notifying user.

#### Scenario: Silent memory load
- **WHEN** session starts
- **THEN** MEMORY.md content is included in system prompt section silently

#### Scenario: Memory reference expansion
- **WHEN** MEMORY.md contains `[[other-memory]]` links
- **THEN** linked memories are NOT auto-expanded (loaded separately when needed)

### Requirement: Explicit memory save

The system SHALL provide a `remember` tool/command for users to explicitly save memories.

#### Scenario: User saves memory
- **WHEN** user calls `remember("I prefer single-file solutions over abstractions")`
- **THEN** system immediately saves a feedback memory without LLM confirmation

#### Scenario: Memory saved confirmation
- **WHEN** memory is successfully saved
- **THEN** system confirms with brief message "Saved memory: <name>"

### Requirement: Memory deletion

The system SHALL provide a `forget` tool/command for users to delete memories.

#### Scenario: User deletes memory
- **WHEN** user calls `forget("old-decision")`
- **THEN** system removes the memory file and updates MEMORY.md index

#### Scenario: Delete non-existent memory
- **WHEN** user calls `forget("nonexistent")`
- **THEN** system returns error "Memory not found: nonexistent"

### Requirement: Memory query

The system SHALL provide a `recall` tool/command for users to query memories.

#### Scenario: List all memories
- **WHEN** user calls `recall()` without arguments
- **THEN** system returns MEMORY.md content

#### Scenario: Query specific memory
- **WHEN** user calls `recall("user-role")`
- **THEN** system returns full content of user-role.md

### Requirement: Auto extraction at session end

The system SHALL analyze conversation at session end to extract potential memories via LLM.

#### Scenario: Extract feedback from conversation
- **WHEN** session ends with user saying "no not that, use the real database"
- **THEN** LLM extracts feedback memory: "integration tests must hit real database"

#### Scenario: Extract project context
- **WHEN** session ends with discussion about legal compliance
- **THEN** LLM extracts project memory about compliance constraints

#### Scenario: No extraction if nothing notable
- **WHEN** session ends with routine conversation
- **THEN** no memories are extracted

### Requirement: Memory linking

The system SHALL support `[[memory-name]]` syntax for linking between memories.

#### Scenario: Link in memory content
- **WHEN** memory A references memory B with `[[auth-decision]]`
- **THEN** link is preserved in file for future reference

#### Scenario: Link resolution
- **WHEN** reading memory with `[[auth-decision]]`
- **THEN** user can manually navigate to linked memory (not auto-resolved)

### Requirement: Memory content structure

Feedback and project memories SHALL include structured content with Why and How to apply sections.

#### Scenario: Feedback memory structure
- **WHEN** saving feedback memory
- **THEN** content includes: rule, **Why:** (reason), **How to apply:** (when it applies)

#### Scenario: Project memory structure
- **WHEN** saving project memory
- **THEN** content includes: fact/decision, **Why:** (motivation), **How to apply:** (how to shape suggestions)