"""File system tools: Read, Write, Edit."""

from __future__ import annotations

from pathlib import Path

from tools import tool


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


__all__ = ["read_file", "write_file", "edit_file"]