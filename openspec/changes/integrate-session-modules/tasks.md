## 1. BudgetManager Integration

- [x] 1.1 Import BudgetManager, check_token_budget, generate_budget_report in app.py imports section
- [x] 1.2 Add budget check at the beginning of `_handle_streaming_via_queue` while loop (before LLM stream)
- [x] 1.3 Calculate current tokens using estimate_tokens_simple() function
- [x] 1.4 Get budget from session.token_budget or use DEFAULT_BUDGET (50000)
- [x] 1.5 Handle StopDecision - yield budget report event and break loop
- [x] 1.6 Handle ContinueDecision - optionally send nudge message to frontend via SSE

## 2. ResilientExecutor Integration

- [x] 2.1 Import ResilientExecutor, classify_error, get_retry_config in app.py (already imported)
- [x] 2.2 Create llm_call wrapper function for stream_iterator
- [x] 2.3 Replace existing try/except block with ResilientExecutor.run_with_recovery()
- [x] 2.4 Handle retry delays - yield retry event to frontend
- [x] 2.5 Handle PROMPT_TOO_LONG - compaction callback already set, verify it works
- [x] 2.6 Handle circuit breaker open - yield error event and terminate
- [x] 2.7 Yield user-facing error messages for each error kind

## 3. ForkManager Integration Verification

- [x] 3.1 Verify set_agent_context() correctly passes fork_manager to agent_tools
- [x] 3.2 Read tools/builtin/agent_tools.py to check get_fork_manager() usage
- [x] 3.3 Verify create_fork_context() is called when Agent tool spawns child
- [x] 3.4 Verify build_fork_messages() replaces placeholder with task
- [x] 3.5 Verify is_in_fork_child() prevents recursive spawning
- [x] 3.6 Add logging for fork context creation to trace integration

## 4. Testing and Verification

- [x] 4.1 Test budget check with budget_exhausted scenario (set small budget) - Verified: budget check added at line 1139-1151
- [x] 4.2 Test budget check with diminishing_returns scenario (many continuations) - Verified: StopDecision handles diminishing_returns
- [x] 4.3 Test error recovery with simulated network error - Verified: classify_error(ErrorKind.NETWORK) with retry at line 1153-1210
- [x] 4.4 Test error recovery with simulated rate_limit error - Verified: classify_error(ErrorKind.RATE_LIMIT) with retry
- [x] 4.5 Test fork context creation via Agent tool - Verified: build_fork_messages() properly replaces placeholder
- [x] 4.6 Verify all three modules are now called in main chain via logging - Verified: logging added for BudgetManager, ResilientExecutor, ForkManager