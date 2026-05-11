"""Skill pack for bundling skills and tools."""

from __future__ import annotations

import json
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from skills.models import Skill


@dataclass
class ToolMeta:
    """Metadata for a tool in a skill pack.

    Attributes:
        name: Tool name
        description: Tool description
        code: Optional tool implementation code
    """

    name: str
    description: str = ""
    code: str | None = None


@dataclass
class SkillPack:
    """Bundled skills and tools for distribution.

    Attributes:
        name: Pack name
        version: Pack version (semver)
        skills: List of skills in this pack
        tools: List of tool metadata
        author: Pack author
        description: Pack description
        dependencies: Required skill packs
    """

    name: str
    version: str = "1.0.0"
    skills: list[Skill] = field(default_factory=list)
    tools: list[ToolMeta] = field(default_factory=list)
    author: str = ""
    description: str = ""
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "skills": [s.to_dict() for s in self.skills],
            "tools": [
                {"name": t.name, "description": t.description, "code": t.code}
                for t in self.tools
            ],
            "author": self.author,
            "description": self.description,
            "dependencies": self.dependencies,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SkillPack:
        """Deserialize from dictionary."""
        skills = [Skill.from_dict(s) for s in data.get("skills", [])]
        tools = [
            ToolMeta(
                name=t["name"],
                description=t.get("description", ""),
                code=t.get("code"),
            )
            for t in data.get("tools", [])
        ]
        return cls(
            name=data["name"],
            version=data.get("version", "1.0.0"),
            skills=skills,
            tools=tools,
            author=data.get("author", ""),
            description=data.get("description", ""),
            dependencies=data.get("dependencies", []),
        )


def create_pack(name: str, skills_dir: Path, output_path: Path | None = None) -> SkillPack:
    """Create a skill pack from a directory of skill JSON files.

    Args:
        name: Pack name
        skills_dir: Directory containing skill JSON files
        output_path: Optional path to save the pack file

    Returns:
        SkillPack instance
    """
    skills = []
    tools = []

    if skills_dir.is_dir():
        for f in sorted(skills_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                skill = Skill.from_dict(data)
                skills.append(skill)

                # Extract tool metadata from skill
                for tool_name in skill.tools:
                    tools.append(ToolMeta(name=tool_name))
            except (json.JSONDecodeError, KeyError):
                continue

    pack = SkillPack(name=name, skills=skills, tools=tools)

    if output_path:
        save_pack(pack, output_path)

    return pack


def save_pack(pack: SkillPack, path: Path) -> None:
    """Save a skill pack to a file (.pack = tar.gz).

    Args:
        pack: SkillPack to save
        path: Output file path
    """
    path = path.with_suffix(".pack")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write manifest
        manifest_path = Path(tmpdir) / "manifest.json"
        manifest_path.write_text(json.dumps(pack.to_dict(), indent=2))

        # Write skill files
        skills_dir = Path(tmpdir) / "skills"
        skills_dir.mkdir()
        for skill in pack.skills:
            skill_file = skills_dir / f"{skill.name}.json"
            skill_file.write_text(json.dumps(skill.to_dict(), indent=2))

        # Create tarball
        with tarfile.open(path, "w:gz") as tar:
            tar.add(manifest_path, arcname="manifest.json")
            tar.add(skills_dir, arcname="skills")


def load_pack(path: Path) -> SkillPack:
    """Load a skill pack from a file.

    Args:
        path: Pack file path (.pack)

    Returns:
        SkillPack instance
    """
    path = path.with_suffix(".pack") if not path.suffix == ".pack" else path

    with tarfile.open(path, "r:gz") as tar:
        # Extract manifest
        manifest_member = tar.getmember("manifest.json")
        manifest_file = tar.extractfile(manifest_member)
        if manifest_file is None:
            raise ValueError("Pack missing manifest.json")

        manifest_data = json.loads(manifest_file.read().decode())
        pack = SkillPack.from_dict(manifest_data)

        # Extract skills if needed
        for member in tar.getmembers():
            if member.name.startswith("skills/") and member.name.endswith(".json"):
                skill_file = tar.extractfile(member)
                if skill_file:
                    skill_data = json.loads(skill_file.read().decode())
                    # Update skill in pack if it exists
                    skill_name = Path(member.name).stem
                    for s in pack.skills:
                        if s.name == skill_name:
                            # Update with full data
                            pack.skills[pack.skills.index(s)] = Skill.from_dict(skill_data)

    return pack


__all__ = ["SkillPack", "ToolMeta", "create_pack", "save_pack", "load_pack"]