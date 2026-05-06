"""Built-in tools available to all agents.

Provides file system, shell, web, and search capabilities
inspired by Claude Code's tool set.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx

from tools import tool


# ============================================================
# Utility tools
# ============================================================


@tool(description="Get the current date and time")
def current_time() -> str:
    import datetime
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")


@tool(
    name="calculator",
    description="Evaluate a mathematical expression. Use Python arithmetic syntax.",
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "A mathematical expression, e.g. '2 + 2' or 'sqrt(144)'",
            }
        },
        "required": ["expression"],
    },
)
def calculator(expression: str) -> str:
    import math
    allowed_names = {k: v for k, v in math.__dict__.items() if not k.startswith("_")}
    allowed_names.update({"abs": abs, "round": round, "min": min, "max": max})
    try:
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return str(result)
    except Exception as e:
        return f"Error: {e}"


# ============================================================
# File system tools
# ============================================================


@tool(
    name="Read",
    description="Read the contents of a file. Returns the full file content with line numbers.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to read",
            }
        },
        "required": ["file_path"],
    },
)
def read_file(file_path: str) -> str:
    try:
        content = Path(file_path).read_text(encoding="utf-8")
        lines = content.splitlines()
        numbered = "\n".join(f"{i+1}\t{line}" for i, line in enumerate(lines))
        return numbered
    except Exception as e:
        return f"[Error reading file] {e}"


@tool(
    name="Write",
    description="Write content to a file. Creates parent directories if needed. Overwrites existing files.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to write",
            },
            "content": {
                "type": "string",
                "description": "The full content to write to the file",
            },
        },
        "required": ["file_path", "content"],
    },
)
def write_file(file_path: str, content: str) -> str:
    try:
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} bytes to {file_path}"
    except Exception as e:
        return f"[Error writing file] {e}"


@tool(
    name="Edit",
    description="Edit a file by replacing the FIRST occurrence of a string with new content. "
                "Use this for targeted edits without rewriting the entire file.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to edit",
            },
            "old_string": {
                "type": "string",
                "description": "The exact text to find and replace (first occurrence only)",
            },
            "new_string": {
                "type": "string",
                "description": "The replacement text",
            },
        },
        "required": ["file_path", "old_string", "new_string"],
    },
)
def edit_file(file_path: str, old_string: str, new_string: str) -> str:
    try:
        p = Path(file_path)
        content = p.read_text(encoding="utf-8")
        if old_string not in content:
            return f"[Error] Could not find the specified text in {file_path}"
        new_content = content.replace(old_string, new_string, 1)
        p.write_text(new_content, encoding="utf-8")
        return f"Successfully edited {file_path}"
    except Exception as e:
        return f"[Error editing file] {e}"


# ============================================================
# Search tools
# ============================================================


@tool(
    name="Glob",
    description="List files matching a glob pattern. Supports ** for recursive matching.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern, e.g. '**/*.py' or 'src/**/*.ts'",
            },
            "root": {
                "type": "string",
                "description": "Root directory to search from (default: current working directory)",
            },
        },
        "required": ["pattern"],
    },
)
def glob_files(pattern: str, root: str | None = None) -> str:
    try:
        base = Path(root).resolve() if root else Path.cwd()
        matches = list(base.rglob(pattern))
        if not matches:
            return f"No files matching '{pattern}' found in {base}"
        result = "\n".join(str(m.relative_to(base)) for m in sorted(matches))
        return f"Found {len(matches)} file(s):\n{result}"
    except Exception as e:
        return f"[Error globbing] {e}"


@tool(
    name="Grep",
    description="Search for a pattern in files. Returns matching lines with file paths and line numbers.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Search pattern (Python regex)",
            },
            "path": {
                "type": "string",
                "description": "Directory or file to search in (default: current directory)",
            },
            "include": {
                "type": "string",
                "description": "Only search files matching this glob, e.g. '*.py'",
            },
        },
        "required": ["pattern"],
    },
)
def grep_files(pattern: str, path: str | None = None, include: str | None = None) -> str:
    try:
        search_path = Path(path).resolve() if path else Path.cwd()

        cmd = ["grep", "-rn", "--color=never"]
        if include:
            cmd.extend([f"--include={include}"])
        cmd.extend([pattern, str(search_path)])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            if len(lines) > 200:
                lines = lines[:200]
                lines.append(f"... (truncated, {len(lines)} lines shown)")
            return "\n".join(lines)
        elif result.returncode == 1:
            return f"No matches found for '{pattern}'"
        else:
            return f"[Error] {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return "[Error] grep timed out after 30s"
    except Exception as e:
        return f"[Error grepping] {e}"


# ============================================================
# Shell tool
# ============================================================


@tool(
    name="Bash",
    description="Execute a shell command and return its output. "
                "Use this to run scripts, compilers, tests, or any CLI tool. "
                "Timeout is 60 seconds. Interactive commands are not supported.",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
            "workdir": {
                "type": "string",
                "description": "Working directory for the command (default: current directory)",
            },
        },
        "required": ["command"],
    },
)
def bash(command: str, workdir: str | None = None) -> str:
    try:
        cwd = workdir if workdir else None
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=cwd,
        )
        output = []
        if result.stdout:
            output.append(result.stdout.strip()[:5000])
        if result.stderr:
            output.append(f"[stderr]\n{result.stderr.strip()[:2000]}")
        if result.returncode != 0:
            output.insert(0, f"Exit code: {result.returncode}")
        return "\n".join(output) if output else f"(completed with no output, exit code {result.returncode})"
    except subprocess.TimeoutExpired:
        return "[Error] Command timed out after 60s"
    except Exception as e:
        return f"[Error] {e}"


# ============================================================
# Web tools
# ============================================================


@tool(
    name="WebFetch",
    description="Fetch and read the content of a URL. "
                "Use this to access web pages, APIs, or documentation. "
                "Returns the page content converted to markdown.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The full URL to fetch (including https://)",
            },
        },
        "required": ["url"],
    },
)
def web_fetch(url: str) -> str:
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()
        content = response.text
        # Simple HTML-to-text extraction for common cases
        if "<html" in content[:500].lower():
            import re
            # Remove scripts and styles
            content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
            content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
            # Remove tags
            content = re.sub(r'<[^>]+>', ' ', content)
            # Collapse whitespace
            content = re.sub(r'\s+', ' ', content).strip()
            if len(content) > 10000:
                content = content[:10000] + "\n... (truncated)"

        return content[:10000]
    except httpx.HTTPStatusError as e:
        return f"[HTTP {e.response.status_code}] {e.response.text[:500]}"
    except Exception as e:
        return f"[Error fetching URL] {e}"


# ============================================================
# Agent tool (meta) — simplified delegation
# ============================================================


@tool(
    name="Agent",
    description="Delegate a sub-task to a specialized sub-agent. "
                "Use this for complex or independent sub-tasks that should be handled "
                "with focused attention. The sub-agent will report back results.",
    parameters={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "A clear, self-contained description of the sub-task to delegate",
            },
        },
        "required": ["task"],
    },
)
def agent_delegate(task: str) -> str:
    """Delegation is a placeholder for future multi-agent orchestration.
    Currently returns guidance for the calling LLM to handle the task itself."""
    return (
        f"[Agent delegation requested, but sub-agent dispatch is not yet implemented. "
        f"Please handle this task directly using your available tools.]\n"
        f"Requested task: {task}"
    )


@tool(
    name="WebSearch",
    description="Search the internet for current information. Uses DuckDuckGo — no API key required.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
        },
        "required": ["query"],
    },
)
def web_search(query: str) -> str:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return f"No results found for '{query}'"
        lines = []
        for r in results:
            title = r.get("title", "")
            href = r.get("href", "")
            body = r.get("body", "")
            lines.append(f"- {title}\n  {href}\n  {body}")
        return "\n\n".join(lines)[:5000]
    except Exception as e:
        return f"[WebSearch error] {e}"
