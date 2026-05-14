## ADDED Requirements

### Requirement: Docker sandbox for Bash execution

The system SHALL execute Bash commands in Docker container when sandbox mode is enabled.

#### Scenario: Sandbox enabled
- **WHEN** configuration has `sandbox_enabled: true`
- **THEN** all Bash commands execute in Docker container

#### Scenario: Sandbox disabled
- **WHEN** configuration has `sandbox_enabled: false`
- **THEN** Bash commands execute directly on host (for development)

### Requirement: Container isolation

The system SHALL isolate Bash execution in ephemeral Docker containers.

#### Scenario: Ephemeral container
- **WHEN** Bash command is executed
- **THEN** temporary container is created and removed after execution

#### Scenario: Network isolation
- **WHEN** sandbox mode is enabled
- **THEN** container has configurable network access (disabled by default)

#### Scenario: Filesystem isolation
- **WHEN** sandbox mode is enabled
- **THEN** only specified directories are mounted into container

### Requirement: Sandbox configuration

The system SHALL support configurable sandbox parameters.

#### Scenario: Mount directories
- **WHEN** configuration specifies `sandbox_read_dirs: ["/tmp", "./src"]`
- **THEN** these directories are mounted read-only into container

#### Scenario: Write directories
- **WHEN** configuration specifies `sandbox_write_dirs: ["./output"]`
- **THEN** these directories are mounted with write access

#### Scenario: Network access
- **WHEN** configuration specifies `sandbox_network: true`
- **THEN** container has network access for curl, wget, etc.

### Requirement: Timeout handling

The system SHALL enforce execution timeout for sandboxed commands.

#### Scenario: Default timeout
- **WHEN** Bash command is executed without explicit timeout
- **THEN** default timeout of 120 seconds is enforced

#### Scenario: Timeout exceeded
- **WHEN** command execution exceeds timeout
- **THEN** container is terminated and error is returned