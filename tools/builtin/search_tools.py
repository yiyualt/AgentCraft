"""Search tools: Glob, Grep."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tools import tool


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


__all__ = ["glob_files", "grep_files"]