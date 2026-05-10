"""Skill data model."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Skill:
    name: str
    description: str
    tools: list[str] = field(default_factory=list)
    instructions: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> Skill:
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            tools=data.get("tools", []),
            instructions=data.get("instructions", ""),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "tools": self.tools,
            "instructions": self.instructions,
        }
