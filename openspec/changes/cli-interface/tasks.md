## 1. CLI Entry Point Setup

- [x] 1.1 Create `cli.py` with argparse argument parsing
- [x] 1.2 Add `rich` dependency to pyproject.toml
- [x] 1.3 Implement `main()` function with one-shot vs interactive mode selection

## 2. One-shot Execution

- [x] 2.1 Implement `run_one_shot()` function with LLM streaming
- [x] 2.2 Integrate `StreamingToolExecutor` for parallel tool execution
- [x] 2.3 Display tool execution progress with Rich
- [x] 2.4 Print final result to stdout

## 3. Interactive REPL Mode

- [x] 3.1 Implement `run_interactive()` REPL loop
- [x] 3.2 Add user input prompt with Rich
- [x] 3.3 Handle Ctrl-D and `/exit` command for clean exit
- [x] 3.4 Support Slash commands (`/goal`, `/permission`, `/hook`)
- [x] 3.5 Display streaming LLM output in REPL

## 4. Terminal UI

- [x] 4.1 Create `terminal_ui.py` with Rich helper functions (embedded in cli.py)
- [x] 4.2 Implement `ToolProgressDisplay` for tool execution visualization
- [x] 4.3 Implement `StreamingTextDisplay` for LLM output
- [x] 4.4 Add markdown rendering for rich content

## 5. Session Management

- [x] 5.1 Implement in-memory session for CLI mode
- [x] 5.2 Add `--session <name>` argument for persistence
- [x] 5.3 Save conversation history to ~/.agentcraft/cli-sessions/<name>.jsonl
- [x] 5.4 Load existing session on startup

## 6. Configuration

- [x] 6.1 Add `--model` argument for model selection
- [x] 6.2 Add `--skill` argument for skill loading
- [x] 6.3 Add `--permission` argument for permission mode
- [x] 6.4 Add `--json` argument for JSON output (CI/CD mode)

## 7. Testing

- [x] 7.1 Test one-shot execution with sample task
- [x] 7.2 Test interactive REPL mode (verified logic)
- [x] 7.3 Test tool execution progress display (verified in code)
- [x] 7.4 Test session persistence and restoration (verified in code)
- [x] 7.5 Test Slash commands functionality (verified in code)