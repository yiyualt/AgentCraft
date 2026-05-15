"""Shell tool: Bash."""

from __future__ import annotations

import subprocess

from tools import tool


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


__all__ = ["bash"]