## ADDED Requirements

### Requirement: Budget check before each tool turn

The system SHALL check token budget before each LLM call in the tool loop. When budget is exceeded or diminishing returns detected, the system SHALL gracefully terminate and generate a budget report.

#### Scenario: Budget under threshold - continue
- **WHEN** current tokens < 90% of budget AND continuation count < MAX_CONTINUATIONS (10)
- **THEN** system continues with nudge message showing progress percentage

#### Scenario: Budget exceeded - stop with report
- **WHEN** current tokens >= 90% of budget
- **THEN** system stops execution and returns budget report with total tokens, percentage, and duration

#### Scenario: Diminishing returns detected - stop with report
- **WHEN** current tokens >= MIN_TOKENS_FOR_DIMINISHING (3000) AND continuation count >= MAX_CONTINUATIONS (10) AND last two deltas < DIMINISHING_THRESHOLD (200)
- **THEN** system stops execution and returns budget report with diminishing_returns flag set to true

### Requirement: Budget tracker persistence per session

The system SHALL maintain a BudgetTracker per session_id to track continuation count, last delta tokens, and total tokens used.

#### Scenario: New session gets new tracker
- **WHEN** a new session_id is encountered
- **THEN** system creates a new BudgetTracker instance for that session

#### Scenario: Existing session uses existing tracker
- **WHEN** an existing session_id is encountered
- **THEN** system retrieves the existing BudgetTracker for that session

### Requirement: Budget report generation

The system SHALL generate a formatted budget report when execution stops due to budget reasons.

#### Scenario: Budget report format
- **WHEN** budget causes execution stop
- **THEN** system generates markdown report with:
  - Total used tokens and percentage
  - Budget limit
  - Execution turns count
  - Duration in milliseconds
  - Stop reason (diminishing_returns or budget_exhausted)