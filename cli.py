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
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
load_dotenv()

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
from sessions import SessionManager, TokenCalculator, CompactionManager, CompactionConfig, PermissionMode
from sessions.vector_memory import MockEmbeddingModel
from skills import SkillLoader, default_skill_dirs

# ===== Config =====
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-default")
CLI_SESSION_DIR = Path.home() / ".agentcraft" / "cli-sessions"

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


def build_system_prompt(session: CLISession, messages: list[dict] | None = None, skill_name: str | None = None) -> str:
    """Build system prompt for LLM.

    Args:
        session: CLI session with goal
        messages: Current messages (used to extract user task for memory search)
        skill_name: Optional specific skill
    """
    parts = []

    # Add skill listing
    skill_listing = _skill_loader.build_skill_listing()
    if skill_listing:
        parts.append(skill_listing)

    # Add goal if set
    if session.goal:
        parts.append(f"\n<goal>\nGoal: {session.goal}\nComplete this goal before ending the session.\n</goal>")

    # Add memory context - 根据用户任务动态检索
    try:
        store = get_memory_store()

        if messages:
            # 提取最新用户消息，进行相关记忆检索
            user_task = None
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if content and not content.startswith("/"):  # 排除 slash 命令
                        user_task = content
                        break

            if user_task:
                # 搜索最相关的 5 条记忆（按 hybrid 排序）
                relevant_memories = store.search_hybrid(user_task, limit=5)

                if relevant_memories:
                    # 加载 top 3 的完整内容（不管 similarity 值）
                    # MockEmbeddingModel similarity 低，但排序正确
                    memory_lines = ["\n<relevant_memories>\n\n"]
                    for entry in relevant_memories[:3]:  # 只取 top 3
                        memory_lines.append(f"## {entry.name}\n\n")
                        memory_lines.append(f"{entry.content}\n\n")
                    memory_lines.append("</relevant_memories>\n")

                    parts.append("".join(memory_lines))
                    logger.info(f"[MEMORY] Loaded {min(3, len(relevant_memories))} relevant memories for task")

        # 如果没有相关记忆或没有任务，加载 index 作为备选
        if not parts or not any("<relevant_memories>" in p for p in parts):
            memory_index = store.get_index_content()
            if memory_index:
                parts.append(f"\n<memory_index>\n{memory_index}\n</memory_index>\n")
    except Exception as e:
        logger.debug(f"[MEMORY] Load failed: {e}")
        pass  # Memory loading is optional

    return "\n\n".join(parts) if parts else ""


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
                cmd_result = handle_slash_command(user_input, session)
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
            break


def handle_slash_command(cmd: str, session: CLISession) -> str | None:
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
"""

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