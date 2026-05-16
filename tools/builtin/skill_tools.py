"""Skill Tool — invoke skill on demand."""

from __future__ import annotations

import json
from typing import Any

from tools import tool
from skills import SkillLoader


# Global skill loader reference (set by gateway)
_skill_loader: SkillLoader | None = None


def set_skill_loader(loader: SkillLoader) -> None:
    """Set the global skill loader reference."""
    global _skill_loader
    _skill_loader = loader


def get_skill_loader() -> SkillLoader | None:
    """Get the global skill loader reference."""
    return _skill_loader


@tool(
    name="Skill",
    description="""Execute a skill within the main conversation.

When users ask you to perform tasks, check if any of the available skills match. Skills provide specialized capabilities and domain knowledge.

When users reference a "slash command" or "/<something>", they are referring to a skill. Use this tool to invoke it.

How to invoke:
- Set `skill` to the exact name of an available skill (no leading slash). For plugin-namespaced skills use the fully qualified `plugin:skill` form.
- Set `args` to pass optional arguments.

IMPORTANT:
- Available skills are listed in system-reminder messages in the conversation
- Only invoke a skill that appears in that list, or one the user explicitly typed as `/<name>` in their message. Never guess or invent a skill name from training data, otherwise do not call this tool
- When a skill matches the user's request, this is a BLOCKING REQUIREMENT: invoke the relevant Skill tool BEFORE generating any other response about the task
- NEVER mention a skill without actually calling this tool
- Do not invoke a skill that is already running
- Do not use this tool for built-in CLI commands (like /help, /clear, etc.)
- If you see a <skill> tag in the current conversation turn, the skill has ALREADY been loaded - follow the instructions directly instead of calling this tool again""",
    parameters={
        "type": "object",
        "properties": {
            "skill": {
                "type": "string",
                "description": "The name of a skill from the available-skills list. Do not guess or invent a skill name.",
            },
            "args": {
                "type": "string",
                "description": "Optional arguments for the skill",
            },
        },
        "required": ["skill"],
    },
)
def invoke_skill(skill: str, args: str | None = None) -> str:
    """Invoke a skill and return its content.

    Returns:
        Skill content as a special JSON structure that signals skill loading.
    """
    if _skill_loader is None:
        return json.dumps({
            "success": False,
            "error": "Skill loader not initialized",
        })

    skill_obj = _skill_loader.get_skill(skill)
    if skill_obj is None:
        return json.dumps({
            "success": False,
            "error": f"Skill not found: {skill}",
        })

    # Return skill content in a special format
    # The gateway will detect this and inject the full skill instructions
    return json.dumps({
        "success": True,
        "skill_name": skill,
        "skill_description": skill_obj.description,
        "skill_instructions": skill_obj.instructions,
        "skill_tools": skill_obj.tools,
        "args": args,
    })


__all__ = ["invoke_skill", "set_skill_loader", "get_skill_loader"]