## ADDED Requirements

### Requirement: Plugin package metadata

The system SHALL support plugin package metadata in pyproject.toml.

#### Scenario: Plugin entry point
- **WHEN** plugin package defines entry point in `[project.entry-points."agentcraft.plugins"]`
- **THEN** plugin is discoverable via entry point mechanism

#### Scenario: Plugin metadata fields
- **WHEN** plugin package is defined
- **THEN** metadata includes: name, version, description, dependencies

#### Scenario: Plugin dependencies
- **WHEN** plugin has dependencies in pyproject.toml
- **THEN** dependencies are installed when plugin is pip installed

### Requirement: Plugin installation

The system SHALL support plugin installation via pip.

#### Scenario: Install from PyPI
- **WHEN** user runs `pip install agentcraft-plugin-telegram`
- **THEN** plugin is installed and entry point registered

#### Scenario: Install from local
- **WHEN** user runs `pip install ./plugins/my-plugin`
- **THEN** local plugin is installed in editable mode

#### Scenario: Install from git
- **WHEN** user runs `pip install git+https://github.com/user/plugin`
- **THEN** plugin is installed from git repository

### Requirement: Plugin versioning

The system SHALL support plugin versioning and compatibility checks.

#### Scenario: Version compatibility
- **WHEN** plugin declares `agentcraft_version: ">=1.0,<2.0"`
- **THEN** plugin only loads if AgentCraft version matches

#### Scenario: Version mismatch
- **WHEN** plugin version requirement doesn't match AgentCraft version
- **THEN** plugin is skipped with warning log

#### Scenario: Plugin upgrade
- **WHEN** user runs `pip install --upgrade agentcraft-plugin-telegram`
- **THEN** plugin is upgraded to latest compatible version

### Requirement: Plugin discovery

The system SHALL discover installed plugins at startup.

#### Scenario: Auto discovery
- **WHEN** AgentCraft starts
- **THEN** all installed plugins with entry points are discovered and loaded

#### Scenario: Discovery log
- **WHEN** plugins are discovered
- **THEN** loaded plugins are logged with name and version

#### Scenario: Duplicate handling
- **WHEN** multiple plugins have same name
- **THEN** only first discovered plugin is loaded, duplicates are logged as warnings

### Requirement: Plugin configuration

The system SHALL support plugin-specific configuration.

#### Scenario: Plugin config section
- **WHEN** AgentCraft config file has `[plugins.telegram]` section
- **THEN** config is passed to TelegramPlugin via PluginContext

#### Scenario: Plugin default config
- **WHEN** plugin config section is missing
- **THEN** plugin receives empty config dict