"""Session management for AgentCraft - 应用层."""

from sessions.manager import SessionManager
from sessions.prompt_builder import PromptBuilder, build_system_prompt
from sessions.memory_loader import MemoryLoader, load_relevant_memories
from sessions.tool_loop import run_tool_loop, clean_orphan_tool_messages
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
    load_hooks_from_config,
    create_hook_executor,
    DEFAULT_HOOKS_PATH,
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

__all__ = [
    # Session management
    "SessionManager",
    # Prompt & Memory (应用层)
    "PromptBuilder",
    "build_system_prompt",
    "MemoryLoader",
    "load_relevant_memories",
    # Tool Loop (应用层执行)
    "run_tool_loop",
    "clean_orphan_tool_messages",
    # Memory strategies
    "SlidingWindowStrategy",
    "SummaryStrategy",
    "HybridStrategy",
    # Compaction
    "CompactionConfig",
    "CompactionState",
    "CompactionManager",
    # Fork
    "ForkContext",
    "ForkManager",
    "FORK_PLACEHOLDER",
    "FORK_CHILD_BOILERPLATE",
    # Budget
    "BudgetTracker",
    "BudgetManager",
    "BudgetDecision",
    "ContinueDecision",
    "StopDecision",
    "check_token_budget",
    "get_budget_for_task",
    "generate_budget_report",
    "estimate_tokens_simple",
    "DEFAULT_BUDGET",
    # Error recovery
    "ErrorKind",
    "RetryStrategy",
    "CircuitState",
    "ResilientExecutor",
    "classify_error",
    "get_retry_config",
    "calculate_delay",
    "format_error_message",
    "ERROR_MESSAGES",
    "RETRY_CONFIGS",
    # Hooks
    "HookEvent",
    "HookInput",
    "HookOutput",
    "HookMatcher",
    "HookExecutor",
    "load_hooks_from_config",
    "create_hook_executor",
    "DEFAULT_HOOKS_PATH",
    # Goal
    "GoalState",
    "GoalManager",
    "check_stop_goal",
    # Permission
    "PermissionMode",
    "PermissionRuleKind",
    "PermissionResult",
    "PermissionRule",
    "PermissionChecker",
    "PermissionPattern",
    "PermissionAuditLog",
    "PermissionAuditor",
    "YoloClassifier",
    "RuleSource",
    "MultiSourceRuleManager",
    "DEFAULT_RULES",
]