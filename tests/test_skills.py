"""Unit tests for Skills system."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from skills.models import Skill
from skills.loader import SkillLoader, default_skill_dirs


@pytest.fixture
def temp_skill_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def skill_loader(temp_skill_dir):
    return SkillLoader([temp_skill_dir])


def _write_skill(dir: Path, name: str, **overrides):
    data = {
        "name": name,
        "description": f"Skill: {name}",
        "tools": ["read_file", "bash"],
        "instructions": f"Instructions for {name}",
        **overrides,
    }
    (dir / f"{name}.json").write_text(json.dumps(data))


# ============================================================
# Skill Model
# ============================================================


class TestSkillModel:
    def test_from_dict(self):
        s = Skill.from_dict({
            "name": "test",
            "description": "a test skill",
            "tools": ["bash", "read_file"],
            "instructions": "Do the thing.",
        })
        assert s.name == "test"
        assert s.description == "a test skill"
        assert s.tools == ["bash", "read_file"]
        assert s.instructions == "Do the thing."

    def test_from_dict_minimal(self):
        s = Skill.from_dict({"name": "minimal"})
        assert s.name == "minimal"
        assert s.description == ""
        assert s.tools == []
        assert s.instructions == ""

    def test_to_dict(self):
        s = Skill(name="x", description="d", tools=["t1"], instructions="i")
        d = s.to_dict()
        assert d["name"] == "x"
        assert d["tools"] == ["t1"]


# ============================================================
# SkillLoader
# ============================================================


class TestSkillLoader:
    def test_load_single(self, skill_loader, temp_skill_dir):
        _write_skill(temp_skill_dir, "code-expert")
        skill_loader.load()
        assert skill_loader.get_skill("code-expert") is not None

    def test_load_multiple(self, skill_loader, temp_skill_dir):
        _write_skill(temp_skill_dir, "a")
        _write_skill(temp_skill_dir, "b")
        skill_loader.load()
        assert len(skill_loader.list_skills()) == 2

    def test_list_skills(self, skill_loader, temp_skill_dir):
        _write_skill(temp_skill_dir, "code-expert")
        _write_skill(temp_skill_dir, "file-manager")
        skill_loader.load()
        names = {s.name for s in skill_loader.list_skills()}
        assert names == {"code-expert", "file-manager"}

    def test_get_skill_missing(self, skill_loader):
        assert skill_loader.get_skill("nonexistent") is None

    def test_later_dir_overrides(self, temp_skill_dir):
        d1 = temp_skill_dir / "d1"
        d2 = temp_skill_dir / "d2"
        d1.mkdir()
        d2.mkdir()
        _write_skill(d1, "x", instructions="v1")
        _write_skill(d2, "x", instructions="v2")
        loader = SkillLoader([d1, d2])
        loader.load()
        assert loader.get_skill("x").instructions == "v2"

    def test_skips_invalid_json(self, skill_loader, temp_skill_dir):
        (temp_skill_dir / "bad.json").write_text("not json")
        skill_loader.load()
        assert skill_loader.list_skills() == []

    def test_skips_missing_name(self, skill_loader, temp_skill_dir):
        (temp_skill_dir / "noname.json").write_text('{"tools": []}')
        skill_loader.load()
        assert skill_loader.list_skills() == []

    def test_load_empty_dir(self, skill_loader):
        skill_loader.load()
        assert skill_loader.list_skills() == []

    def test_builtin_skills_exist(self):
        """Verify built-in skill JSON files are valid."""
        loader = SkillLoader(default_skill_dirs())
        loader.load()
        skills = loader.list_skills()
        names = {s.name for s in skills}
        assert "code-expert" in names
        assert "file-manager" in names


# ============================================================
# build_prompt
# ============================================================


class TestBuildPrompt:
    def test_empty_names(self, skill_loader):
        assert skill_loader.build_prompt([]) == ""

    def test_single_skill(self, skill_loader, temp_skill_dir):
        _write_skill(temp_skill_dir, "test-skill",
                     description="A test skill",
                     instructions="Do X.\nThen do Y.")
        skill_loader.load()
        prompt = skill_loader.build_prompt(["test-skill"])
        assert "test-skill" in prompt
        assert "A test skill" in prompt
        assert "Do X." in prompt
        assert "Then do Y." in prompt

    def test_unknown_skill_filtered(self, skill_loader):
        assert skill_loader.build_prompt(["nonexistent"]) == ""

    def test_mixed_known_unknown(self, skill_loader, temp_skill_dir):
        _write_skill(temp_skill_dir, "real-one")
        skill_loader.load()
        prompt = skill_loader.build_prompt(["real-one", "fake-one"])
        assert "real-one" in prompt


# ============================================================
# Gateway Skills Endpoint
# ============================================================


class TestGatewaySkills:
    @pytest.fixture
    def api_client(self):
        from app import app
        return TestClient(app)

    def test_list_skills(self, api_client):
        resp = api_client.get("/v1/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        names = {s["name"] for s in data}
        assert "code-expert" in names
        assert "file-manager" in names

    def test_skill_format(self, api_client):
        resp = api_client.get("/v1/skills")
        skill = resp.json()[0]
        assert "name" in skill
        assert "description" in skill
        assert "tools" in skill
        assert "instructions" in skill


# ============================================================
# Session Skills Field
# ============================================================


class TestSessionSkills:
    @pytest.fixture
    def api_client(self):
        import gateway
        gateway._session_manager = __import__('sessions.manager', fromlist=['SessionManager']).SessionManager(":memory:")
        return TestClient(gateway.app)

    def test_create_session_default_skills(self, api_client):
        resp = api_client.post("/v1/sessions", json={"name": "s"})
        assert resp.json()["skills"] == ""

    def test_update_session_skills(self, api_client):
        created = api_client.post("/v1/sessions", json={"name": "s"}).json()
        resp = api_client.patch(
            f"/v1/sessions/{created['id']}",
            json={"skills": "code-expert,file-manager"},
        )
        assert resp.status_code == 200
        assert resp.json()["skills"] == "code-expert,file-manager"

    def test_skills_field_allowed(self, api_client):
        created = api_client.post("/v1/sessions", json={"name": "s"}).json()
        resp = api_client.patch(
            f"/v1/sessions/{created['id']}",
            json={"skills": "code-expert"},
        )
        assert resp.json()["skills"] == "code-expert"
