## ADDED Requirements

### Requirement: Multiple API keys per provider

The system SHALL support multiple API keys for each provider in configuration.

#### Scenario: Config multiple keys
- **WHEN** configuration includes `api_keys: ["key1", "key2", "key3"]`
- **THEN** system stores all keys for rotation

#### Scenario: Key rotation on failure
- **WHEN** current API key fails (rate limit, auth error)
- **THEN** system automatically switches to next key in list

#### Scenario: All keys exhausted
- **WHEN** all API keys for a provider fail
- **THEN** system falls back to next provider (if configured)

### Requirement: Provider priority configuration

The system SHALL support provider priority ordering in configuration.

#### Scenario: Priority ordering
- **WHEN** configuration specifies `priority: 1` for DeepSeek and `priority: 2` for Anthropic
- **THEN** DeepSeek is tried first, Anthropic is fallback

#### Scenario: Equal priority providers
- **WHEN** multiple providers have same priority
- **THEN** system tries them in configuration order

### Requirement: Auth failure tracking

The system SHALL track API key failure counts and cooldown periods.

#### Scenario: Failure count increment
- **WHEN** API key fails
- **THEN** failure count is incremented for that key

#### Scenario: Cooldown activation
- **WHEN** key failure count exceeds threshold (default: 3)
- **THEN** key enters cooldown period (default: 60 seconds)

#### Scenario: Cooldown expiry
- **WHEN** cooldown period expires
- **THEN** key is available for retry again