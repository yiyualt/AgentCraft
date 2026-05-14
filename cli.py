"""AgentCraft CLI - Terminal interface for AI agent.

Usage:
    agentcraft "任务描述"            # One-shot mode
    agentcraft -i                    # Interactive REPL mode
    agentcraft -i --session dev      # Interactive with session persistence
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
load_dotenv()

# Logger setup
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich.live import Live
from rich.text import Text

# Import core components
from openai import OpenAI
import httpx

from tools import get_default_registry, UnifiedToolRegistry
from tools.builtin import *  # noqa: F401,F403 — register built-in tools
from tools.pptx_tools import *  # noqa: F401,F403 — register PPTX tools
from tools.agent_executor import AgentExecutor, set_agent_executor
from tools.skill_tools import *  # noqa: F401,F403 — register Skill tool
from tools.memory_tools import get_memory_store, set_memory_store, remember, forget, recall  # noqa: F401,F403
from streaming_executor import StreamingToolExecutor, is_concurrency_safe, ToolResult
from sessions import SessionManager, TokenCalculator, CompactionManager, CompactionConfig, PermissionMode, ForkManager
from sessions.vector_memory import MockEmbeddingModel
from skills import SkillLoader, default_skill_dirs
from core import PromptBuilder, MemoryLoader
from acp import AgentControlPlane, AcpConfig
from tools.sandbox import SandboxExecutor, SandboxConfig
from automation import CronStore, CronScheduler
from automation.types import CronJob, CronExpressionSchedule, CronDelivery, DeliveryMode, SessionTarget
from automation.scheduler import set_scheduler

# ===== Config =====
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-default")
CLI_SESSION_DIR = Path.home() / ".agentcraft" / "cli-sessions"

# Sandbox config
SANDBOX_ENABLED = os.getenv("SANDBOX_ENABLED", "false").lower() == "true"
SANDBOX_NETWORK = os.getenv("SANDBOX_NETWORK", "false").lower() == "true"
SANDBOX_HOST_BIN = os.getenv("SANDBOX_HOST_BIN", "false").lower() == "true"
SANDBOX_PIP_PACKAGES = os.getenv("SANDBOX_PIP_PACKAGES", "").split(",") if os.getenv("SANDBOX_PIP_PACKAGES") else []
SANDBOX_READ_DIRS = os.getenv("SANDBOX_READ_DIRS", "").split(",") if os.getenv("SANDBOX_READ_DIRS") else []
SANDBOX_WRITE_DIRS = os.getenv("SANDBOX_WRITE_DIRS", "").split(",") if os.getenv("SANDBOX_WRITE_DIRS") else []

# ===== Console =====
console = Console()

# ===== LLM Client =====
client = OpenAI(
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
    http_client=httpx.Client(trust_env=False, timeout=300),
)

# ===== Global State =====
_session_manager = SessionManager()
_skill_loader = SkillLoader(default_skill_dirs())
_skill_loader.load()
_registry = UnifiedToolRegistry(get_default_registry())

# Initialize SandboxExecutor (if enabled)
_sandbox_executor: SandboxExecutor | None = None
if SANDBOX_ENABLED:
    sandbox_config = SandboxConfig(
        network_disabled=not SANDBOX_NETWORK,
        mount_host_bin=SANDBOX_HOST_BIN,
        pip_packages=SANDBOX_PIP_PACKAGES,
        read_dirs=SANDBOX_READ_DIRS,
        write_dirs=SANDBOX_WRITE_DIRS,
    )
    _sandbox_executor = SandboxExecutor(sandbox_config)
    logger.info(f"[Sandbox] Executor initialized: network={SANDBOX_NETWORK}, host_bin={SANDBOX_HOST_BIN}")

# Initialize Agent executor
_agent_executor = AgentExecutor(
    llm_client=client,
    registry=_registry,
    session_manager=_session_manager,
)
set_agent_executor(_agent_executor)

# Initialize CronScheduler
_cron_store = CronStore()
_cron_scheduler = CronScheduler(
    store=_cron_store,
    agent_executor_factory=lambda: _agent_executor,
)
set_scheduler(_cron_scheduler)
logger.info("[Cron] Scheduler initialized")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="agentcraft",
        description="AI Agent CLI - Execute tasks with LLM and tools",
    )

    # Positional argument for one-shot message
    parser.add_argument(
        "message",
        nargs="?",
        help="Task message for one-shot execution",
    )

    # Mode selection
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Enter interactive REPL mode",
    )

    # Configuration
    parser.add_argument(
        "--model",
        default="deepseek-chat",
        help="LLM model to use (default: deepseek-chat)",
    )
    parser.add_argument(
        "--session",
        metavar="NAME",
        help="Session name for persistence",
    )
    parser.add_argument(
        "--skill",
        metavar="NAME",
        help="Load specific skill",
    )
    parser.add_argument(
        "--permission",
        choices=["default", "acceptEdits", "bypass", "auto", "plan"],
        default="default",
        help="Permission mode (default: default)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON (for CI/CD)",
    )
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Enable sandbox mode (execute tools in Docker container)",
    )
    parser.add_argument(
        "--sandbox-network",
        action="store_true",
        help="Allow network access in sandbox",
    )

    return parser.parse_args()


class CLISession:
    """In-memory session for CLI mode with optional persistence."""

    def __init__(self, name: str | None = None, model: str = "deepseek-chat"):
        self.name = name
        self.model = model
        self.messages: list[dict[str, Any]] = []
        self.permission_mode = PermissionMode.DEFAULT
        self.goal: str | None = None
        self.skills: list[str] = []

        # Load existing session if name provided
        if name:
            self._load()

    def _load(self) -> None:
        """Load session from file."""
        if not self.name:
            return

        session_file = CLI_SESSION_DIR / f"{self.name}.jsonl"
        if session_file.exists():
            with open(session_file, "r") as f:
                for line in f:
                    if line.strip():
                        self.messages.append(json.loads(line))
            console.print(f"[green]Session '{self.name}' loaded ({len(self.messages)} messages)[/green]")

    def save(self) -> None:
        """Save session to file."""
        if not self.name:
            return

        CLI_SESSION_DIR.mkdir(parents=True, exist_ok=True)
        session_file = CLI_SESSION_DIR / f"{self.name}.jsonl"
        with open(session_file, "w") as f:
            for msg in self.messages:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        console.print(f"[green]Session saved to {session_file}[/green]")

    def add_message(self, role: str, content: str, **kwargs) -> None:
        """Add message to session."""
        msg = {"role": role, "content": content, **kwargs}
        self.messages.append(msg)

    def get_messages(self) -> list[dict[str, Any]]:
        """Get all messages."""
        return self.messages.copy()

    def clear(self) -> None:
        """Clear session."""
        self.messages.clear()
        self.goal = None


class ToolProgressDisplay:
    """Display tool execution progress."""

    def __init__(self):
        self._tools: dict[str, dict] = {}
        self._spinner_texts: list[str] = []

    def on_tool_start(self, tool_call_id: str, tool_name: str) -> None:
        """Tool started."""
        self._tools[tool_call_id] = {
            "name": tool_name,
            "status": "running",
            "started_at": time.time(),
        }
        console.print(f"[yellow]▸ Tool: {tool_name}[/yellow] executing...")

    def on_tool_complete(self, tool_call_id: str, result: str) -> None:
        """Tool completed."""
        if tool_call_id in self._tools:
            tool = self._tools[tool_call_id]
            duration = int((time.time() - tool["started_at"]) * 1000)
            tool["status"] = "complete"

            # Truncate result
            result_preview = result[:200] if len(result) > 200 else result
            console.print(f"[green]✓ Tool: {tool['name']}[/green] ({duration}ms) → {result_preview}")

    def on_tool_error(self, tool_call_id: str, error: str) -> None:
        """Tool error."""
        if tool_call_id in self._tools:
            tool = self._tools[tool_call_id]
            tool["status"] = "error"
            console.print(f"[red]✗ Tool: {tool['name']}[/red] Error: {error}")


# Initialize ACP (Agent Control Plane) for multi-agent tasks
_fork_manager = ForkManager(
    session_manager=_session_manager,
    token_calculator=TokenCalculator(),
)
_acp_config = AcpConfig(
    max_children=10,
    default_timeout=180,
    recursion_protection=True,
)
_acp = AgentControlPlane(
    llm_client=client,
    registry=_registry,
    session_manager=_session_manager,
    fork_manager=_fork_manager,
    config=_acp_config,
)
_agent_executor.set_fork_manager(_fork_manager)
logger.info("[ACP] AgentControlPlane initialized: max_children=10")

# Global prompt builder (uses core module)
_prompt_builder = PromptBuilder(skill_loader=_skill_loader)


def build_system_prompt(session: CLISession, messages: list[dict] | None = None, skill_name: str | None = None) -> str:
    """Build system prompt for LLM.

    Args:
        session: CLI session with goal
        messages: Current messages (used to extract user task for memory search)
        skill_name: Optional specific skill
    """
    return _prompt_builder.build(
        messages=messages,
        goal=session.goal,
        skill_name=skill_name,
    )


async def execute_tool_loop(
    messages: list[dict[str, Any]],
    model: str,
    session: CLISession,
    progress_display: ToolProgressDisplay,
    json_output: bool = False,
) -> str:
    """Execute LLM + tool loop until complete."""

    tools = _registry.list_tools()
    n_turns = 0
    final_content = ""

    while True:
        # Build system prompt (根据当前消息动态检索相关记忆)
        system_prompt = build_system_prompt(session, messages)
        if system_prompt:
            # Insert system message if not present
            if not any(m["role"] == "system" for m in messages):
                messages.insert(0, {"role": "system", "content": system_prompt})

        # Call LLM (streaming)
        if not json_output:
            console.print("[bold blue]Agent:[/bold blue]")

        call_kwargs = {"model": model, "messages": messages, "tools": tools, "stream": True}

        try:
            stream = client.chat.completions.create(**call_kwargs)
        except Exception as e:
            console.print(f"[red]LLM Error: {e}[/red]")
            break

        # Process streaming response
        assistant_message = {"role": "assistant", "content": "", "tool_calls": []}
        current_tool_call = None
        current_tool_args = ""

        for event in stream:
            delta = event.choices[0].delta

            if delta.content:
                assistant_message["content"] += delta.content
                if not json_output:
                    console.print(delta.content, end="")

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    if tc.id and tc.function.name:
                        # New tool call
                        current_tool_call = {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": ""},
                        }
                        assistant_message["tool_calls"].append(current_tool_call)
                        current_tool_args = ""

                    if tc.function.arguments and current_tool_call:
                        current_tool_call["function"]["arguments"] += tc.function.arguments
                        current_tool_args += tc.function.arguments

        if not json_output:
            console.print()  # New line after content

        messages.append(assistant_message)
        final_content = assistant_message["content"]

        # Check for tool calls
        tool_calls = assistant_message.get("tool_calls")
        if not tool_calls:
            break

        n_turns += 1
        if n_turns > 50:
            console.print("[red]Tool limit exceeded[/red]")
            break

        # Execute tools with StreamingToolExecutor
        executor = StreamingToolExecutor(
            registry=_registry,
            max_concurrency=10,
            session_id=session.name,
            sandbox_executor=_sandbox_executor if SANDBOX_ENABLED else None,
        )

        await executor.start_unsafe_executor()

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            try:
                fn_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                fn_args = {}

            progress_display.on_tool_start(tc["id"], fn_name)
            await executor.on_tool_use_block(tc["id"], fn_name, fn_args)

        # Wait for results
        results = await executor.get_results()

        # Display results and append to messages
        for tc in tool_calls:
            tc_id = tc["id"]
            result = results.get(tc_id)

            if result:
                if result.error:
                    progress_display.on_tool_error(tc_id, result.error)
                else:
                    progress_display.on_tool_complete(tc_id, result.content)
                messages.append(result.to_tool_message())

        # Handle Skill tool
        for tc in tool_calls:
            if tc["function"]["name"] == "Skill":
                result = results.get(tc["id"])
                if result and not result.error:
                    try:
                        skill_data = json.loads(result.content)
                        if skill_data.get("success") and skill_data.get("skill_instructions"):
                            skill_content = f"<skill>\nSkill '{skill_data['skill_name']}' loaded.\n\n{skill_data['skill_instructions']}\n</skill>"
                            messages.append({"role": "assistant", "content": skill_content})
                            console.print(f"[cyan]Skill loaded: {skill_data['skill_name']}[/cyan]")
                    except json.JSONDecodeError:
                        pass

    return final_content


async def run_one_shot(
    message: str,
    model: str,
    session: CLISession,
    json_output: bool = False,
) -> str:
    """Execute one-shot task."""
    progress_display = ToolProgressDisplay()

    # Add user message
    session.add_message("user", message)
    messages = session.get_messages()

    # Execute
    result = await execute_tool_loop(messages, model, session, progress_display, json_output)

    # Save session if named
    session.save()

    return result


async def run_interactive(
    model: str,
    session: CLISession,
) -> None:
    """Interactive REPL mode."""
    # Start cron scheduler
    _cron_scheduler.start()
    logger.info("[Cron] Scheduler started")

    console.print(Panel.fit(
        "[bold]AgentCraft CLI[/bold]\n"
        f"Model: {model}\n"
        f"Session: {session.name or 'memory-only'}\n"
        "Type your message, or use /help for commands",
        border_style="blue",
    ))

    progress_display = ToolProgressDisplay()

    while True:
        try:
            # Prompt for input
            user_input = Prompt.ask("\n[bold green]You:[/bold green]")

            if not user_input.strip():
                continue

            # Handle slash commands
            if user_input.startswith("/"):
                cmd_result = await handle_slash_command(user_input, session)
                if cmd_result:
                    console.print(cmd_result)
                continue

            # Add user message
            session.add_message("user", user_input)
            messages = session.get_messages()

            # Execute
            await execute_tool_loop(messages, model, session, progress_display)

            # Save after each turn
            session.save()

        except KeyboardInterrupt:
            console.print("\n[yellow]Use /exit to quit[/yellow]")
        except EOFError:
            console.print("\n[green]Goodbye![/green]")
            session.save()
            _cron_scheduler.stop()
            logger.info("[Cron] Scheduler stopped")
            break


# ===== Cron Command Helpers =====

def _cron_list() -> str:
    """List all cron jobs."""
    jobs = _cron_scheduler.list_jobs()
    if not jobs:
        return "[yellow]No scheduled jobs[/yellow]"

    lines = ["[bold]Scheduled Jobs:[/bold]\n\n"]
    for job in jobs:
        status_color = "green" if job.state.status.value == "ok" else "yellow" if job.state.status.value == "running" else "red"
        enabled_mark = "✓" if job.enabled else "✗"
        lines.append(f"  [{status_color}]{enabled_mark} {job.id}[/{status_color}]: {job.name}\n")
        lines.append(f"    Schedule: {job.schedule.kind} ({job.schedule.expr if hasattr(job.schedule, 'expr') else '-'})\n")
        lines.append(f"    Status: {job.state.status.value}, Runs: {job.state.run_count}\n")
        if job.state.next_run_at:
            lines.append(f"    Next run: {datetime.fromtimestamp(job.state.next_run_at).strftime('%Y-%m-%d %H:%M')}\n")
        lines.append("\n")
    return "".join(lines)


def _cron_show(job_id: str) -> str:
    """Show job details."""
    if not job_id:
        return "[red]Usage: /cron show <job_id>[/red]"

    job = _cron_scheduler.get_job(job_id)
    if not job:
        return f"[red]Job not found: {job_id}[/red]"

    lines = [f"[bold]Job: {job.name}[/bold]\n\n"]
    lines.append(f"  ID: {job.id}\n")
    lines.append(f"  Enabled: {job.enabled}\n")
    lines.append(f"  Schedule: {job.schedule.kind}\n")
    if hasattr(job.schedule, 'expr'):
        lines.append(f"    Expression: {job.schedule.expr}\n")
    if hasattr(job.schedule, 'tz'):
        lines.append(f"    Timezone: {job.schedule.tz}\n")
    lines.append(f"  Task: {job.task[:100]}...\n")
    lines.append(f"  Agent Type: {job.agent_type}\n")
    lines.append(f"  Timeout: {job.timeout}s\n")
    lines.append(f"\n  [bold]State:[/bold]\n")
    lines.append(f"    Status: {job.state.status.value}\n")
    lines.append(f"    Runs: {job.state.run_count}, Errors: {job.state.error_count}\n")
    if job.state.last_run_at:
        lines.append(f"    Last run: {datetime.fromtimestamp(job.state.last_run_at).strftime('%Y-%m-%d %H:%M:%S')}\n")
    if job.state.last_result:
        lines.append(f"    Last result: {job.state.last_result[:100]}...\n")
    if job.state.last_error:
        lines.append(f"    Last error: {job.state.last_error[:100]}\n")

    # Run history
    runs = _cron_store.get_runs(job_id, limit=5)
    if runs:
        lines.append(f"\n  [bold]Recent Runs:[/bold]\n")
        for run in runs:
            run_time = datetime.fromtimestamp(run["run_at"]).strftime('%Y-%m-%d %H:%M')
            status_color = "green" if run["status"] == "ok" else "red"
            lines.append(f"    [{status_color}]{run_time}[/{status_color}]: {run['status']} ({run.get('duration_ms', 0)}ms)\n")

    return "".join(lines)


def _cron_add(args: str) -> str:
    """Add new cron job.

    Usage: /cron add <name> <cron_expr> <task>
    Example: /cron add hello-world "*/1 * * * *" "echo hello world"
    Or: /cron add hello-world */1 * * * * echo hello world  (auto-parse 5 fields)
    """
    if not args:
        return "[red]Usage: /cron add <name> <cron_expr> <task>[/red]\n  Example: /cron add hello-world \"*/1 * * * *\" \"echo hello world\""

    # Parse with potential quotes or 5-field cron expression
    import re

    # Try quoted format first: name "expr" "task"
    quoted_match = re.match(r'(\S+)\s+"([^"]+)"\s+"([^"]+)"', args)
    if quoted_match:
        name = quoted_match.group(1)
        expr = quoted_match.group(2)
        task = quoted_match.group(3)
    else:
        # Try split approach: name followed by 5 cron fields then task
        parts = args.split()
        if len(parts) >= 7:  # name + 5 cron fields + task
            name = parts[0]
            expr = " ".join(parts[1:6])  # 5 cron fields
            task = " ".join(parts[6:])
        elif len(parts) >= 3:
            # Fallback: name expr task (expr might be quoted or single field)
            name = parts[0]
            expr = parts[1] if len(parts) == 3 else " ".join(parts[1:6])
            task = parts[-1] if len(parts) == 3 else " ".join(parts[6:])
        else:
            return "[red]Usage: /cron add <name> <cron_expr> <task>[/red]"

    import uuid
    job_id = f"cron-{uuid.uuid4().hex[:8]}"

    from automation.types import CronExpressionSchedule
    job = CronJob(
        id=job_id,
        name=name,
        schedule=CronExpressionSchedule(expr=expr),
        task=task,
        delivery=CronDelivery(mode=DeliveryMode.NONE),
    )

    _cron_scheduler.add_job(job)
    return f"[green]✓ Created job: {job_id}[/green]\n  Name: {name}\n  Schedule: {expr}\n  Task: {task[:50]}..."


def _cron_delete(job_id: str) -> str:
    """Delete cron job."""
    if not job_id:
        return "[red]Usage: /cron del <job_id>[/red]"

    if _cron_scheduler.delete_job(job_id):
        return f"[yellow]Deleted job: {job_id}[/yellow]"
    return f"[red]Job not found: {job_id}[/red]"


def _cron_enable(job_id: str) -> str:
    """Enable cron job."""
    if not job_id:
        return "[red]Usage: /cron enable <job_id>[/red]"

    if _cron_scheduler.enable_job(job_id):
        return f"[green]Enabled job: {job_id}[/green]"
    return f"[red]Job not found: {job_id}[/red]"


def _cron_disable(job_id: str) -> str:
    """Disable cron job."""
    if not job_id:
        return "[red]Usage: /cron disable <job_id>[/red]"

    if _cron_scheduler.disable_job(job_id):
        return f"[yellow]Disabled job: {job_id}[/yellow]"
    return f"[red]Job not found: {job_id}[/red]"


async def handle_slash_command(cmd: str, session: CLISession) -> str | None:
    """Handle slash commands."""
    parts = cmd.strip().split(" ", 1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if command in ("/exit", "/quit"):
        session.save()
        raise EOFError  # Trigger exit

    if command == "/help":
        return """
[bold]Commands:[/bold]
  /help         Show this help
  /exit         Exit REPL
  /clear        Clear session history
  /goal <text>  Set goal condition
  /permission <mode> Set permission mode (default|bypass|auto|plan)
  /session      Show session info
  /remember <text> Save to memory for future sessions
  /forget <name> Delete a saved memory
  /recall [name] List memories or show specific memory

[bold]ACP (Agent Control Plane):[/bold]
  /acp          Show ACP status
  /spawn <task> [type] Spawn child agent (types: explore, general-purpose, plan)
  /children     List child agents
  /wait [timeout] Wait for all children to complete

[bold]Cron (Scheduled Tasks):[/bold]
  /cron         Show cron status and jobs
  /cron list    List all scheduled jobs
  /cron show <id> Show job details
  /cron add <name> <expr> <task> Add new job
  /cron del <id> Delete job
  /cron enable <id> Enable job
  /cron disable <id> Disable job
"""

    # ACP commands
    if command == "/acp":
        status = _acp.get_status()
        return f"""
[bold]ACP Status:[/bold]
  Active: {status['active']} / {status['max_children']}
  Completed: {status['completed']}
  Failed: {status['failed']}
  Children: {len(status['children'])}

[bold]Children:[/bold]
""" + "\n".join([
    f"  • {cid}: {c['task'][:40]}... ({c['state']}, {c['elapsed']:.1f}s)"
    for cid, c in status['children'].items()
]) if status['children'] else "  (none)"

    if command == "/spawn":
        if not args:
            return "[red]Usage: /spawn <task> [agent_type][/red]"
        # Parse task and agent_type
        parts2 = args.rsplit(" ", 1)
        if len(parts2) == 2 and parts2[1] in ("explore", "general-purpose", "plan"):
            task = parts2[0]
            agent_type = parts2[1]
        else:
            task = args
            agent_type = "general-purpose"

        try:
            child = _acp.spawn_child(task=task, agent_type=agent_type)
            return f"[green]✓ Spawned child: {child.child_id}[/green]\n  Task: {task}\n  Type: {agent_type}"
        except Exception as e:
            return f"[red]Spawn failed: {e}[/red]"

    if command == "/children":
        status = _acp.get_status()
        if not status['children']:
            return "[yellow]No child agents[/yellow]"
        lines = ["[bold]Child Agents:[/bold]\n"]
        for cid, c in status['children'].items():
            state = c['state']
            state_color = "green" if state == "completed" else "yellow" if state == "running" else "red"
            lines.append(f"  [{state_color}]{cid}[/{state_color}]: {c['task'][:50]}...\n")
            lines.append(f"    State: {state}, Elapsed: {c['elapsed']:.1f}s\n")
        return "".join(lines)

    if command == "/wait":
        timeout = int(args) if args else 120
        console.print(f"[yellow]Waiting for children (timeout: {timeout}s)...[/yellow]")
        try:
            results = await asyncio.wait_for(_acp.wait_all(), timeout=timeout)
            lines = ["[bold]Results:[/bold]\n\n"]
            for cid, result in results.items():
                lines.append(f"[cyan]{cid}:[/cyan]\n{result[:200]}...\n\n")
            return "".join(lines)
        except asyncio.TimeoutError:
            return "[red]Timeout waiting for children[/red]"

    # Cron commands
    if command == "/cron":
        # Parse sub-command
        if not args or args == "list":
            return _cron_list()
        parts = args.split(" ", 1)
        subcmd = parts[0]
        subargs = parts[1] if len(parts) > 1 else ""

        if subcmd == "list":
            return _cron_list()
        elif subcmd == "show":
            return _cron_show(subargs)
        elif subcmd == "add":
            return _cron_add(subargs)
        elif subcmd == "del":
            return _cron_delete(subargs)
        elif subcmd == "enable":
            return _cron_enable(subargs)
        elif subcmd == "disable":
            return _cron_disable(subargs)
        else:
            return f"[red]Unknown cron command: {subcmd}[/red]"

    if command == "/clear":
        session.clear()
        return "[yellow]Session cleared[/yellow]"

    if command == "/goal":
        if args:
            session.goal = args
            return f"[green]Goal set: {args}[/green]"
        else:
            session.goal = None
            return "[yellow]Goal cleared[/yellow]"

    if command == "/permission":
        mode_map = {
            "default": PermissionMode.DEFAULT,
            "bypass": PermissionMode.BYPASS,
            "auto": PermissionMode.AUTO,
            "plan": PermissionMode.PLAN,
        }
        mode = mode_map.get(args.lower())
        if mode:
            session.permission_mode = mode
            return f"[green]Permission mode: {mode.value}[/green]"
        return f"[red]Unknown mode: {args}[/red]"

    if command == "/session":
        return f"""
[bold]Session Info:[/bold]
  Name: {session.name or 'memory-only'}
  Messages: {len(session.messages)}
  Model: {session.model}
  Goal: {session.goal or 'none'}
  Permission: {session.permission_mode.value}
"""

    # Memory commands
    if command == "/remember":
        if not args:
            return "[red]Usage: /remember <content>[/red]"
        store = get_memory_store()
        name = args[:30].replace(" ", "-").lower()
        store.save(name, "feedback", args + "\n\n**Why:** User preference\n**How to apply:** Apply when relevant")
        return f"[green]Saved memory: {name}[/green]"

    if command == "/forget":
        if not args:
            return "[red]Usage: /forget <name>[/red]"
        store = get_memory_store()
        if store.delete(args):
            return f"[yellow]Forgot memory: {args}[/yellow]"
        return f"[red]Memory not found: {args}[/red]"

    if command == "/recall":
        store = get_memory_store()
        if args:
            # 搜索模式
            results = store.search_hybrid(args, limit=5)
            if not results:
                entry = store.load(args)  # 尝试按名字加载
                if entry:
                    return f"[bold]{entry.name}[/bold]\n\n{entry.content}"
                return f"[red]Memory not found: {args}[/red]"

            # 返回搜索结果
            lines = [f"[bold]Search results for \"{args}\":[/bold]\n\n"]
            for entry in results:
                score = f" (score: {entry.similarity:.2f})" if entry.similarity > 0 else ""
                lines.append(f"• [cyan]{entry.name}[/cyan]{score}: {entry.content[:100]}...\n")
            return "".join(lines)
        else:
            index = store.get_index_content()
            if index:
                return index
            return "[yellow]No memories saved. Use /remember to save.[/yellow]"

    return f"[red]Unknown command: {command}[/red]"


async def main_async() -> None:
    """Main entry point."""
    args = parse_args()

    # Handle sandbox override from CLI args
    global SANDBOX_ENABLED, _sandbox_executor
    if args.sandbox and not SANDBOX_ENABLED:
        SANDBOX_ENABLED = True
        sandbox_config = SandboxConfig(
            network_disabled=not args.sandbox_network,
            mount_host_bin=SANDBOX_HOST_BIN,
            pip_packages=SANDBOX_PIP_PACKAGES,
            read_dirs=SANDBOX_READ_DIRS,
            write_dirs=SANDBOX_WRITE_DIRS,
        )
        _sandbox_executor = SandboxExecutor(sandbox_config)
        logger.info(f"[Sandbox] Enabled via CLI: network={args.sandbox_network}")

    # Create session
    session = CLISession(name=args.session, model=args.model)

    # Set permission mode
    mode_map = {
        "default": PermissionMode.DEFAULT,
        "acceptEdits": PermissionMode.ACCEPT_EDITS,
        "bypass": PermissionMode.BYPASS,
        "auto": PermissionMode.AUTO,
        "plan": PermissionMode.PLAN,
    }
    session.permission_mode = mode_map.get(args.permission, PermissionMode.DEFAULT)

    # Load skill if specified
    if args.skill:
        session.skills.append(args.skill)

    # Determine mode
    if args.interactive:
        await run_interactive(args.model, session)
    elif args.message:
        result = await run_one_shot(args.message, args.model, session, args.json)
        if args.json:
            # JSON output for CI/CD
            output = {
                "result": result,
                "model": args.model,
                "session": args.session,
                "messages": len(session.messages),
            }
            print(json.dumps(output, ensure_ascii=False))
    else:
        # No message and not interactive → show help
        console.print("[yellow]Provide a message for one-shot mode, or use -i for interactive[/yellow]")
        console.print("\n[bold]Usage:[/bold]")
        console.print("  agentcraft \"任务描述\"       # One-shot")
        console.print("  agentcraft -i               # Interactive REPL")


def main() -> None:
    """Entry point for CLI."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
    except EOFError:
        pass  # Clean exit


if __name__ == "__main__":
    main()