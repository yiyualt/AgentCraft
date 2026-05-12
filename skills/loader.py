"""SkillLoader — discover and load skill definitions from directories."""

from __future__ import annotations

import json
import os
from pathlib import Path

from skills.models import Skill


class SkillLoader:
    def __init__(self, directories: list[Path] | None = None):
        self._directories = directories or []
        self._skills: dict[str, Skill] = {}

    def load(self) -> dict[str, Skill]:
        """Scan all directories for .json skill files. Later dirs override earlier ones."""
        self._skills.clear()
        for d in self._directories:
            if not d.is_dir():
                continue
            for f in sorted(d.glob("*.json")):
                try:
                    data = json.loads(f.read_text())
                    skill = Skill.from_dict(data)
                    self._skills[skill.name] = skill
                except (json.JSONDecodeError, KeyError):
                    continue
        return self._skills

    def list_skills(self) -> list[Skill]:
        return list(self._skills.values())

    def get_skill(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def build_skill_listing(self, max_desc_chars: int = 1536) -> str:
        """Build a system reminder listing available skills.

        This is the Claude Code style skill listing - only names and descriptions,
        not full instructions. The model will decide which skill to invoke.

        Args:
            max_desc_chars: Maximum characters per description (default 1536)

        Returns:
            Skill listing string for system reminder injection
        """
        skills = self.list_skills()
        if not skills:
            return ""

        lines = ["The following skills are available for use with the Skill tool:"]
        for s in skills:
            desc = s.description
            # Truncate description if too long
            if len(desc) > max_desc_chars:
                desc = desc[:max_desc_chars] + "..."

            lines.append(f"- {s.name}: {desc}")

        return "\n".join(lines)

    def build_prompt(self, names: list[str]) -> str:
        """Build a system prompt fragment from the given skill names."""
        if not names:
            return ""

        enabled = [
            self._skills[name]
            for name in names
            if name in self._skills
        ]
        if not enabled:
            return ""

        parts = ["## Enabled Skills"]
        for s in enabled:
            parts.append(f"- {s.name}: {s.description}")

        parts.append("\n## Skill Instructions")
        for s in enabled:
            parts.append(f"### {s.name}\n{s.instructions}")

        return "\n".join(parts)


def default_skill_dirs() -> list[Path]:
    """Return the default skill directories: built-in + user."""
    builtin = Path(__file__).resolve().parent / "builtin"
    user = Path(os.path.expanduser("~/.agentcraft/skills"))
    return [builtin, user]
