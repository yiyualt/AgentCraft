## ADDED Requirements

### Requirement: Model configuration

The system SHALL support model configuration in YAML file.

#### Scenario: Model definition
- **WHEN** config file defines model
- **THEN** model has: name, provider, context_window (optional), capabilities (optional)

#### Scenario: Provider association
- **WHEN** model is defined with `provider: deepseek`
- **THEN** model is associated with DeepSeek provider

#### Scenario: Context window override
- **WHEN** model is defined with `context_window: 128000`
- **THEN** this value overrides provider default

### Requirement: Context window detection

The system SHALL detect context window from API response when not configured.

#### Scenario: Detection from response
- **WHEN** LLM API returns model info with context window
- **THEN** system captures and caches context window for future use

#### Scenario: Detection cache
- **WHEN** context window is detected
- **THEN** value is cached in `~/.agentcraft/model-cache.json`

#### Scenario: Cache usage
- **WHEN** model is used again
- **THEN** cached context window is used instead of re-detecting

### Requirement: Model selection

The system SHALL support model selection by name or auto.

#### Scenario: Select by name
- **WHEN** request specifies `model: "deepseek-chat"`
- **THEN** configured model deepseek-chat is used

#### Scenario: Select by alias
- **WHEN** request specifies `model: "fast"`
- **THEN** model aliased to "fast" in config is used

#### Scenario: Auto selection
- **WHEN** request doesn't specify model
- **THEN** default model for provider is used

### Requirement: Model capabilities

The system SHALL track model capabilities for feature enablement.

#### Scenario: Vision capability
- **WHEN** model has `capabilities: ["vision"]`
- **THEN** image input is enabled for this model

#### Scenario: Streaming capability
- **WHEN** model has `capabilities: ["streaming"]`
- **THEN** streaming response is enabled

#### Scenario: Tools capability
- **WHEN** model has `capabilities: ["tools"]`
- **THEN** tool use is enabled

### Requirement: Model fallback chain

The system SHALL support model fallback within provider.

#### Scenario: Model fallback config
- **WHEN** model is defined with `fallback: "deepseek-chat-light"`
- **THEN** if primary model fails, fallback model is tried

#### Scenario: Model fallback chain
- **WHEN** multiple fallbacks are defined
- **THEN** they are tried in order until success or all exhausted