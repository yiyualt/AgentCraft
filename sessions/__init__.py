"""Session management for AgentCraft."""

from sessions.manager import SessionManager
from sessions.tokens import TokenCalculator
from sessions.memory import SlidingWindowStrategy, SummaryStrategy, HybridStrategy
from sessions.compaction import CompactionConfig, CompactionState, CompactionManager
from sessions.fork import ForkContext, ForkManager, FORK_PLACEHOLDER, FORK_CHILD_BOILERPLATE
from sessions.budget import (
    BudgetTracker,
    BudgetManager,
    BudgetDecision,
    ContinueDecision,
    StopDecision,
    check_token_budget,
    get_budget_for_task,
    generate_budget_report,
    estimate_tokens_simple,
    DEFAULT_BUDGET,
)
from sessions.error_recovery import (
    ErrorKind,
    RetryStrategy,
    CircuitState,
    ResilientExecutor,
    classify_error,
    get_retry_config,
    calculate_delay,
    format_error_message,
    ERROR_MESSAGES,
    RETRY_CONFIGS,
)
from sessions.hooks import (
    HookEvent,
    HookInput,
    HookOutput,
    HookMatcher,
    HookExecutor,
)
from sessions.goal import (
    GoalState,
    GoalManager,
    check_stop_goal,
)
from sessions.permission import (
    PermissionMode,
    PermissionRuleKind,
    PermissionResult,
    PermissionRule,
    PermissionChecker,
    PermissionPattern,
    PermissionAuditLog,
    PermissionAuditor,
    YoloClassifier,
    RuleSource,
    MultiSourceRuleManager,
    DEFAULT_RULES,
)
from sessions.vector_memory import (
    EmbeddingModel,
    LocalEmbeddingModel,
    RemoteEmbeddingModel,
    MockEmbeddingModel,
    VectorMemoryStore,
    MemoryEntry,
)