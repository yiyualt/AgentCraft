"""Local skill registry for managing installed skill packs."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from skills.pack import SkillPack, load_pack, save_pack
from skills.models import Skill

logger = logging.getLogger(__name__)


class LocalRegistry:
    """Manage installed skill packs locally.

    Skills are installed to ~/.agentcraft/skills/
    Pack metadata is stored in ~/.agentcraft/registry.json
    """

    def __init__(self, registry_dir: Path | None = None):
        """Initialize local registry.

        Args:
            registry_dir: Directory for registry and skills (default: ~/.agentcraft)
        """
        if registry_dir is None:
            registry_dir = Path.home() / ".agentcraft"

        self.registry_dir = registry_dir
        self.skills_dir = registry_dir / "skills"
        self.registry_file = registry_dir / "registry.json"

        # Ensure directories exist
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        self._installed: dict[str, SkillPack] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        """Load installed packs from registry file."""
        if self.registry_file.exists():
            try:
                data = json.loads(self.registry_file.read_text())
                for pack_data in data.get("installed", []):
                    pack = SkillPack.from_dict(pack_data)
                    self._installed[pack.name] = pack
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load registry: {e}")
                self._installed = {}

    def _save_registry(self) -> None:
        """Save installed packs to registry file."""
        data = {
            "installed": [pack.to_dict() for pack in self._installed.values()],
        }
        self.registry_file.write_text(json.dumps(data, indent=2))

    def install(self, pack: SkillPack) -> None:
        """Install a skill pack.

        Args:
            pack: SkillPack to install
        """
        # Check for existing version
        if pack.name in self._installed:
            existing = self._installed[pack.name]
            logger.info(
                f"Updating {pack.name}: {existing.version} -> {pack.version}"
            )

        # Copy skill files to skills directory
        for skill in pack.skills:
            skill_file = self.skills_dir / f"{skill.name}.json"
            skill_file.write_text(json.dumps(skill.to_dict(), indent=2))
            logger.info(f"Installed skill: {skill.name}")

        # Update registry
        self._installed[pack.name] = pack
        self._save_registry()

        logger.info(f"Installed pack: {pack.name} v{pack.version}")

    def install_from_file(self, pack_path: Path) -> SkillPack:
        """Install a skill pack from a .pack file.

        Args:
            pack_path: Path to the pack file

        Returns:
            Installed SkillPack
        """
        pack = load_pack(pack_path)
        self.install(pack)
        return pack

    def uninstall(self, name: str) -> bool:
        """Uninstall a skill pack.

        Args:
            name: Pack name to uninstall

        Returns:
            True if pack was uninstalled, False if not found
        """
        if name not in self._installed:
            logger.warning(f"Pack not found: {name}")
            return False

        pack = self._installed[name]

        # Remove skill files
        for skill in pack.skills:
            skill_file = self.skills_dir / f"{skill.name}.json"
            if skill_file.exists():
                skill_file.unlink()
                logger.info(f"Removed skill: {skill.name}")

        # Update registry
        del self._installed[name]
        self._save_registry()

        logger.info(f"Uninstalled pack: {name}")
        return True

    def list_installed(self) -> list[SkillPack]:
        """List all installed skill packs.

        Returns:
            List of installed SkillPacks
        """
        return list(self._installed.values())

    def get_pack(self, name: str) -> SkillPack | None:
        """Get an installed pack by name.

        Args:
            name: Pack name

        Returns:
            SkillPack if found, None otherwise
        """
        return self._installed.get(name)

    def list_skills(self) -> list[Skill]:
        """List all installed skills across all packs.

        Returns:
            List of all installed Skills
        """
        skills = []
        for pack in self._installed.values():
            skills.extend(pack.skills)
        return skills

    def get_skill(self, name: str) -> Skill | None:
        """Get an installed skill by name.

        Args:
            name: Skill name

        Returns:
            Skill if found, None otherwise
        """
        for skill in self.list_skills():
            if skill.name == name:
                return skill
        return None

    def search(self, query: str) -> list[SkillPack]:
        """Search installed packs by name or description.

        Args:
            query: Search query

        Returns:
            Matching SkillPacks
        """
        query_lower = query.lower()
        results = []

        for pack in self._installed.values():
            if (
                query_lower in pack.name.lower()
                or query_lower in pack.description.lower()
            ):
                results.append(pack)
            else:
                # Check skills within pack
                for skill in pack.skills:
                    if (
                        query_lower in skill.name.lower()
                        or query_lower in skill.description.lower()
                    ):
                        results.append(pack)
                        break

        return results


__all__ = ["LocalRegistry"]