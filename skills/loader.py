"""SkillLoader — discover and load skill definitions from directories.

Supports both AgentSkills format (SKILL.md) and legacy JSON format.
AgentSkills is the preferred format with YAML frontmatter + Markdown body.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from skills.models import Skill


class SkillLoader:
    def __init__(self, directories: list[Path] | None = None):
        self._directories = directories or []
        self._skills: dict[str, Skill] = {}
        self._last_mtime: dict[Path, float] = {}  # Track last modification time
        self._last_count: int = 0  # Track skill count

    def needs_reload(self) -> bool:
        """Check if skills directory has changes.

        Returns True if:
        - New skill files added
        - Existing skill files modified
        - Skill files deleted
        """
        for d in self._directories:
            if not d.is_dir():
                continue

            # Check SKILL.md files (AgentSkills format)
            for skill_dir in d.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        current_mtime = skill_file.stat().st_mtime
                        last_mtime = self._last_mtime.get(skill_file, 0)
                        if current_mtime > last_mtime:
                            return True

            # Check JSON files (legacy format)
            for f in d.glob("*.json"):
                current_mtime = f.stat().st_mtime
                last_mtime = self._last_mtime.get(f, 0)
                if current_mtime > last_mtime:
                    return True

        # Check if skill count changed
        current_count = len(self._skills)
        if current_count != self._last_count:
            return True

        return False

    def load(self) -> dict[str, Skill]:
        """Scan all directories for skill definitions.

        Supports:
        - AgentSkills format: SKILL.md files with YAML frontmatter
        - Legacy format: .json files

        Later directories override earlier ones.
        """
        self._skills.clear()
        self._last_mtime.clear()

        for d in self._directories:
            if not d.is_dir():
                continue

            # Load AgentSkills format (SKILL.md) - preferred
            for skill_dir in d.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        try:
                            skill = self._parse_skill_md(skill_file)
                            if skill:
                                self._skills[skill.name] = skill
                                # Track modification time
                                self._last_mtime[skill_file] = skill_file.stat().st_mtime
                        except Exception as e:
                            print(f"Failed to load {skill_file}: {e}")
                            continue

            # Load legacy JSON format (backward compatibility)
            for f in sorted(d.glob("*.json")):
                try:
                    data = json.loads(f.read_text())
                    skill = Skill.from_dict(data)
                    # Don't override if SKILL.md already loaded
                    if skill.name not in self._skills:
                        self._skills[skill.name] = skill
                        # Track modification time
                        self._last_mtime[f] = f.stat().st_mtime
                except (json.JSONDecodeError, KeyError):
                    continue

        # Track skill count
        self._last_count = len(self._skills)

        return self._skills

    def _parse_skill_md(self, skill_file: Path) -> Skill | None:
        """Parse SKILL.md file with YAML frontmatter.

        AgentSkills format:
        ---
        name: skill-name
        description: When to use this skill
        metadata:
          version: "1.0"
        ---
        Markdown instructions...
        """
        content = skill_file.read_text()

        # Extract YAML frontmatter
        match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
        if not match:
            return None

        frontmatter_text = match.group(1)
        body = match.group(2).strip()

        # Parse YAML (simple parsing for common fields)
        metadata = {}
        name = None
        description = None

        for line in frontmatter_text.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Handle nested metadata
            if line.startswith("metadata:"):
                # Start metadata block
                continue
            elif ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()

                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]

                if key == "name":
                    name = value
                elif key == "description":
                    description = value
                elif key in ["version", "author"]:
                    metadata[key] = value

        if not name or not description:
            return None

        # Validate name matches directory
        expected_name = skill_file.parent.name
        if name != expected_name:
            print(f"Warning: Skill name '{name}' doesn't match directory '{expected_name}'")

        return Skill(
            name=name,
            description=description,
            instructions=body,
            tools=[],  # AgentSkills doesn't have explicit tools field
        )

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
