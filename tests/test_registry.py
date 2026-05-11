"""Tests for skill registry and pack."""

import json
import pytest
import tempfile
from pathlib import Path

from skills.pack import (
    SkillPack,
    ToolMeta,
    create_pack,
    save_pack,
    load_pack,
)
from skills.registry import LocalRegistry
from skills.models import Skill


class TestToolMeta:
    """Tests for ToolMeta dataclass."""

    def test_default_tool(self):
        """Default tool metadata."""
        tool = ToolMeta(name="echo")

        assert tool.name == "echo"
        assert tool.description == ""
        assert tool.code is None

    def test_full_tool(self):
        """Full tool metadata."""
        tool = ToolMeta(
            name="read_file",
            description="Read file contents",
            code="def read_file(path): return open(path).read()",
        )

        assert tool.name == "read_file"
        assert tool.description == "Read file contents"
        assert tool.code is not None


class TestSkillPack:
    """Tests for SkillPack dataclass."""

    def test_empty_pack(self):
        """Pack with no skills or tools."""
        pack = SkillPack(name="empty")

        assert pack.name == "empty"
        assert pack.version == "1.0.0"
        assert pack.skills == []
        assert pack.tools == []

    def test_pack_with_skills(self):
        """Pack with skills."""
        pack = SkillPack(
            name="test-pack",
            version="2.0.0",
            skills=[
                Skill(name="cat-girl", description="Cat persona"),
                Skill(name="translator", description="Translation skill"),
            ],
            tools=[
                ToolMeta(name="echo"),
            ],
            author="test-author",
            description="Test pack",
        )

        assert pack.name == "test-pack"
        assert pack.version == "2.0.0"
        assert len(pack.skills) == 2
        assert len(pack.tools) == 1
        assert pack.author == "test-author"

    def test_to_dict(self):
        """Serialize to dictionary."""
        pack = SkillPack(
            name="test",
            skills=[Skill(name="s1", description="skill1")],
        )

        data = pack.to_dict()

        assert data["name"] == "test"
        assert data["version"] == "1.0.0"
        assert len(data["skills"]) == 1
        assert data["skills"][0]["name"] == "s1"

    def test_from_dict(self):
        """Deserialize from dictionary."""
        data = {
            "name": "test",
            "version": "1.5.0",
            "skills": [{"name": "s1", "description": "skill1"}],
            "tools": [{"name": "t1", "description": "tool1"}],
            "author": "me",
        }

        pack = SkillPack.from_dict(data)

        assert pack.name == "test"
        assert pack.version == "1.5.0"
        assert len(pack.skills) == 1
        assert pack.skills[0].name == "s1"
        assert len(pack.tools) == 1
        assert pack.tools[0].name == "t1"


class TestCreatePack:
    """Tests for create_pack function."""

    def test_create_from_empty_dir(self):
        """Create pack from empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack = create_pack("empty-pack", Path(tmpdir))

            assert pack.name == "empty-pack"
            assert pack.skills == []

    def test_create_from_skills_dir(self):
        """Create pack from directory with skill files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)

            # Create skill files
            skill1_file = skills_dir / "skill1.json"
            skill1_file.write_text(json.dumps({
                "name": "skill1",
                "description": "First skill",
                "tools": ["echo"],
            }))

            skill2_file = skills_dir / "skill2.json"
            skill2_file.write_text(json.dumps({
                "name": "skill2",
                "description": "Second skill",
            }))

            pack = create_pack("test-pack", skills_dir)

            assert pack.name == "test-pack"
            assert len(pack.skills) == 2
            assert pack.skills[0].name == "skill1"
            assert pack.skills[1].name == "skill2"
            # Tools extracted from skills
            assert len(pack.tools) == 1


class TestSaveLoadPack:
    """Tests for save_pack and load_pack."""

    def test_save_and_load(self):
        """Save pack to file and load it back."""
        pack = SkillPack(
            name="test-pack",
            version="1.0.0",
            skills=[
                Skill(name="s1", description="skill1", instructions="Do X"),
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir) / "test.pack"
            save_pack(pack, pack_path)

            # Load back
            loaded = load_pack(pack_path)

            assert loaded.name == "test-pack"
            assert loaded.version == "1.0.0"
            assert len(loaded.skills) == 1
            assert loaded.skills[0].name == "s1"


class TestLocalRegistry:
    """Tests for LocalRegistry."""

    def test_registry_initialization(self):
        """Registry initializes with empty state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LocalRegistry(Path(tmpdir))

            assert registry.list_installed() == []

    def test_install_pack(self):
        """Install a skill pack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LocalRegistry(Path(tmpdir))

            pack = SkillPack(
                name="test-pack",
                skills=[Skill(name="s1", description="skill1")],
            )

            registry.install(pack)

            installed = registry.list_installed()
            assert len(installed) == 1
            assert installed[0].name == "test-pack"

    def test_install_creates_skill_files(self):
        """Install creates skill JSON files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LocalRegistry(Path(tmpdir))

            pack = SkillPack(
                name="test-pack",
                skills=[
                    Skill(name="s1", description="skill1"),
                    Skill(name="s2", description="skill2"),
                ],
            )

            registry.install(pack)

            # Check skill files exist
            skills_dir = registry.skills_dir
            assert (skills_dir / "s1.json").exists()
            assert (skills_dir / "s2.json").exists()

    def test_uninstall_pack(self):
        """Uninstall a skill pack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LocalRegistry(Path(tmpdir))

            pack = SkillPack(
                name="test-pack",
                skills=[Skill(name="s1", description="skill1")],
            )

            registry.install(pack)
            assert len(registry.list_installed()) == 1

            result = registry.uninstall("test-pack")

            assert result is True
            assert len(registry.list_installed()) == 0
            assert not (registry.skills_dir / "s1.json").exists()

    def test_uninstall_not_found(self):
        """Uninstall pack that doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LocalRegistry(Path(tmpdir))

            result = registry.uninstall("nonexistent")

            assert result is False

    def test_get_pack(self):
        """Get pack by name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LocalRegistry(Path(tmpdir))

            pack = SkillPack(name="test-pack")
            registry.install(pack)

            found = registry.get_pack("test-pack")

            assert found is not None
            assert found.name == "test-pack"

    def test_get_pack_not_found(self):
        """Get pack that doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LocalRegistry(Path(tmpdir))

            found = registry.get_pack("nonexistent")

            assert found is None

    def test_list_skills(self):
        """List all skills across packs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LocalRegistry(Path(tmpdir))

            pack1 = SkillPack(
                name="pack1",
                skills=[Skill(name="s1", description="skill1")],
            )
            pack2 = SkillPack(
                name="pack2",
                skills=[Skill(name="s2", description="skill2")],
            )

            registry.install(pack1)
            registry.install(pack2)

            skills = registry.list_skills()

            assert len(skills) == 2
            assert "s1" in [s.name for s in skills]
            assert "s2" in [s.name for s in skills]

    def test_get_skill(self):
        """Get skill by name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LocalRegistry(Path(tmpdir))

            pack = SkillPack(
                name="test",
                skills=[Skill(name="s1", description="skill1")],
            )

            registry.install(pack)

            skill = registry.get_skill("s1")

            assert skill is not None
            assert skill.name == "s1"

    def test_search_packs(self):
        """Search packs by name or description."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LocalRegistry(Path(tmpdir))

            pack1 = SkillPack(name="cat-pack", description="Cat related skills")
            pack2 = SkillPack(name="code-pack", description="Code generation skills")

            registry.install(pack1)
            registry.install(pack2)

            results = registry.search("cat")

            assert len(results) == 1
            assert results[0].name == "cat-pack"

    def test_search_skills_in_pack(self):
        """Search finds packs by skill content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LocalRegistry(Path(tmpdir))

            pack = SkillPack(
                name="test",
                skills=[Skill(name="translator", description="Translation skill")],
            )

            registry.install(pack)

            results = registry.search("translation")

            assert len(results) == 1
            assert results[0].name == "test"

    def test_update_existing_pack(self):
        """Update an existing pack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = LocalRegistry(Path(tmpdir))

            pack1 = SkillPack(
                name="test",
                version="1.0.0",
                skills=[Skill(name="s1", description="v1 skill")],
            )

            registry.install(pack1)

            pack2 = SkillPack(
                name="test",
                version="2.0.0",
                skills=[Skill(name="s1", description="v2 skill")],
            )

            registry.install(pack2)

            installed = registry.list_installed()
            assert len(installed) == 1
            assert installed[0].version == "2.0.0"

    def test_install_from_file(self):
        """Install pack from .pack file."""
        pack = SkillPack(
            name="file-pack",
            skills=[Skill(name="s1", description="skill1")],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # Save pack file
            pack_path = Path(tmpdir) / "file.pack"
            save_pack(pack, pack_path)

            # Create registry in separate dir
            registry_dir = Path(tmpdir) / "registry"
            registry = LocalRegistry(registry_dir)

            installed = registry.install_from_file(pack_path)

            assert installed.name == "file-pack"
            assert len(registry.list_installed()) == 1

    def test_registry_persistence(self):
        """Registry persists across instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First instance
            registry1 = LocalRegistry(Path(tmpdir))
            pack = SkillPack(name="persist-test")
            registry1.install(pack)

            # Second instance (same directory)
            registry2 = LocalRegistry(Path(tmpdir))

            assert len(registry2.list_installed()) == 1
            assert registry2.get_pack("persist-test") is not None