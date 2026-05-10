"""Unit tests for SessionManager and Gateway session endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sessions.manager import SessionManager
from sessions.models import Session, Message, init_db


@pytest.fixture
def mgr():
    """SessionManager backed by in-memory SQLite."""
    return SessionManager(":memory:")


@pytest.fixture
def api_client():
    """FastAPI TestClient with in-memory SessionManager for test isolation."""
    import gateway
    gateway._session_manager = SessionManager(":memory:")
    return TestClient(gateway.app)


# ============================================================
# Session CRUD
# ============================================================


class TestSessionCreate:
    def test_create_basic(self, mgr):
        s = mgr.create_session("test")
        assert s.name == "test"
        assert s.model == "qwen3:8b"
        assert s.status == "active"
        assert len(s.id) == 12

    def test_create_with_model_and_prompt(self, mgr):
        s = mgr.create_session("dev", model="llama3", system_prompt="Be helpful.")
        assert s.model == "llama3"
        assert s.system_prompt == "Be helpful."

    def test_create_auto_generates_id(self, mgr):
        s1 = mgr.create_session("a")
        s2 = mgr.create_session("b")
        assert s1.id != s2.id


class TestSessionGet:
    def test_get_existing(self, mgr):
        created = mgr.create_session("chat")
        fetched = mgr.get_session(created.id)
        assert fetched is not None
        assert fetched.name == "chat"

    def test_get_nonexistent(self, mgr):
        assert mgr.get_session("nonexistent") is None


class TestSessionList:
    def test_list_active(self, mgr):
        mgr.create_session("a")
        mgr.create_session("b")
        sessions = mgr.list_sessions()
        assert len(sessions) == 2

    def test_list_excludes_archived(self, mgr):
        s = mgr.create_session("archive-me")
        mgr.update_session(s.id, status="archived")
        active = mgr.list_sessions(status="active")
        archived = mgr.list_sessions(status="archived")
        assert len(active) == 0
        assert len(archived) == 1

    def test_list_order_by_updated_at(self, mgr):
        s1 = mgr.create_session("first")
        s2 = mgr.create_session("second")
        sessions = mgr.list_sessions()
        assert sessions[0].id == s2.id  # most recently updated first


class TestSessionUpdate:
    def test_update_name(self, mgr):
        s = mgr.create_session("old")
        updated = mgr.update_session(s.id, name="new")
        assert updated.name == "new"

    def test_update_status(self, mgr):
        s = mgr.create_session("chat")
        updated = mgr.update_session(s.id, status="archived")
        assert updated.status == "archived"

    def test_update_ignores_unknown_fields(self, mgr):
        s = mgr.create_session("chat")
        updated = mgr.update_session(s.id, foo="bar", name="ok")
        assert updated.name == "ok"

    def test_update_nonexistent(self, mgr):
        assert mgr.update_session("no-id", name="x") is None


class TestSessionDelete:
    def test_delete_existing(self, mgr):
        s = mgr.create_session("test")
        assert mgr.delete_session(s.id) is True
        assert mgr.get_session(s.id) is None

    def test_delete_nonexistent(self, mgr):
        assert mgr.delete_session("no-id") is False


# ============================================================
# Message CRUD
# ============================================================


class TestMessageAdd:
    def test_add_user_message(self, mgr):
        s = mgr.create_session("chat")
        msg = mgr.add_message(s.id, "user", "hello")
        assert msg.role == "user"
        assert msg.content == "hello"
        assert msg.session_id == s.id

    def test_add_increments_message_count(self, mgr):
        s = mgr.create_session("chat")
        mgr.add_message(s.id, "user", "a")
        mgr.add_message(s.id, "assistant", "b")
        updated = mgr.get_session(s.id)
        assert updated.message_count == 2

    def test_add_tool_message(self, mgr):
        s = mgr.create_session("chat")
        msg = mgr.add_message(
            s.id, "tool", '{"result": 42}',
            tool_call_id="call_1", name="calculator",
        )
        assert msg.tool_call_id == "call_1"
        assert msg.name == "calculator"


class TestMessageGet:
    def test_get_messages_chronological(self, mgr):
        s = mgr.create_session("chat")
        mgr.add_message(s.id, "user", "first")
        mgr.add_message(s.id, "assistant", "second")
        msgs = mgr.get_messages(s.id)
        assert msgs[0].content == "first"
        assert msgs[1].content == "second"

    def test_get_messages_limit(self, mgr):
        s = mgr.create_session("chat")
        for i in range(10):
            mgr.add_message(s.id, "user", str(i))
        msgs = mgr.get_messages(s.id, limit=5)
        assert len(msgs) == 5

    def test_get_messages_openai_format(self, mgr):
        s = mgr.create_session("chat")
        mgr.add_message(s.id, "user", "hi")
        msgs = mgr.get_messages_openai(s.id)
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hi"
        assert "tool_calls" not in msgs[0]


class TestMessageClear:
    def test_clear_removes_all(self, mgr):
        s = mgr.create_session("chat")
        mgr.add_message(s.id, "user", "a")
        mgr.add_message(s.id, "assistant", "b")
        mgr.clear_messages(s.id)
        assert mgr.get_messages(s.id) == []

    def test_clear_resets_count(self, mgr):
        s = mgr.create_session("chat")
        mgr.add_message(s.id, "user", "a")
        mgr.clear_messages(s.id)
        updated = mgr.get_session(s.id)
        assert updated.message_count == 0


class TestCountTokens:
    def test_rough_estimate(self, mgr):
        s = mgr.create_session("chat")
        mgr.add_message(s.id, "user", "hello world")  # 11 chars -> 5 tokens
        assert mgr.count_tokens(s.id) == 5

    def test_empty_session(self, mgr):
        s = mgr.create_session("chat")
        assert mgr.count_tokens(s.id) == 0


# ============================================================
# Message Isolation
# ============================================================


class TestIsolation:
    def test_messages_isolated_per_session(self, mgr):
        s1 = mgr.create_session("chat1")
        s2 = mgr.create_session("chat2")
        mgr.add_message(s1.id, "user", "hello from 1")
        mgr.add_message(s2.id, "user", "hello from 2")
        msgs1 = mgr.get_messages(s1.id)
        msgs2 = mgr.get_messages(s2.id)
        assert len(msgs1) == 1
        assert len(msgs2) == 1
        assert msgs1[0].content == "hello from 1"

    def test_cascade_delete(self, mgr):
        s = mgr.create_session("chat")
        mgr.add_message(s.id, "user", "test")
        mgr.delete_session(s.id)
        # Messages should be deleted via CASCADE
        conn = init_db(":memory:")
        rows = conn.execute("SELECT * FROM messages WHERE session_id=?", (s.id,)).fetchall()
        assert len(rows) == 0


# ============================================================
# Gateway Session Endpoints
# ============================================================


class TestGatewaySessions:
    def test_create_session(self, api_client):
        resp = api_client.post("/v1/sessions", json={"name": "gw-test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "gw-test"
        assert "id" in data

    def test_create_session_defaults(self, api_client):
        resp = api_client.post("/v1/sessions", json={})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Untitled"

    def test_list_sessions(self, api_client):
        api_client.post("/v1/sessions", json={"name": "a"})
        api_client.post("/v1/sessions", json={"name": "b"})
        resp = api_client.get("/v1/sessions")
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_list_sessions_filter_by_status(self, api_client):
        resp_create = api_client.post("/v1/sessions", json={"name": "archive-me"})
        sid = resp_create.json()["id"]
        api_client.patch(f"/v1/sessions/{sid}", json={"status": "archived"})
        active = api_client.get("/v1/sessions", params={"status": "active"}).json()
        archived = api_client.get("/v1/sessions", params={"status": "archived"}).json()
        assert all(s["status"] == "active" for s in active)
        assert all(s["status"] == "archived" for s in archived)

    def test_get_session(self, api_client):
        created = api_client.post("/v1/sessions", json={"name": "get-me"}).json()
        resp = api_client.get(f"/v1/sessions/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "get-me"

    def test_get_session_404(self, api_client):
        resp = api_client.get("/v1/sessions/nonexistent")
        assert resp.status_code == 404

    def test_update_session(self, api_client):
        created = api_client.post("/v1/sessions", json={"name": "old"}).json()
        resp = api_client.patch(
            f"/v1/sessions/{created['id']}", json={"name": "renamed"}
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "renamed"

    def test_update_session_404(self, api_client):
        resp = api_client.patch("/v1/sessions/nonexistent", json={"name": "x"})
        assert resp.status_code == 404

    def test_delete_session(self, api_client):
        created = api_client.post("/v1/sessions", json={"name": "kill-me"}).json()
        resp = api_client.delete(f"/v1/sessions/{created['id']}")
        assert resp.status_code == 200
        assert resp.json() == {"status": "deleted"}
        # Verify gone
        assert api_client.get(f"/v1/sessions/{created['id']}").status_code == 404

    def test_delete_session_404(self, api_client):
        resp = api_client.delete("/v1/sessions/nonexistent")
        assert resp.status_code == 404

    def test_get_session_messages_empty(self, api_client):
        created = api_client.post("/v1/sessions", json={"name": "msg-test"}).json()
        resp = api_client.get(f"/v1/sessions/{created['id']}/messages")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_session_messages_with_limit(self, api_client):
        import gateway
        created = api_client.post("/v1/sessions", json={"name": "limit-test"}).json()
        sid = created["id"]
        for i in range(5):
            gateway._session_manager.add_message(sid, "user", str(i))
        resp = api_client.get(f"/v1/sessions/{sid}/messages", params={"limit": 2})
        assert len(resp.json()) == 2
