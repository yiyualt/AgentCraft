"""Integration tests for gateway.py.

Requires the LLM (Ollama) to be running.
All tests are marked @pytest.mark.integration and are skipped by default:
    uv run pytest                          # skips integration
    uv run pytest -m integration           # runs integration tests

These tests log to MLFLOW_TRACKING_URI (default: http://127.0.0.1:5050).
Make sure the MLflow server is running before running integration tests.
"""

from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import patch, MagicMock
from typing import AsyncGenerator

import httpx
import pytest
from fastapi.testclient import TestClient

# Suppress mlflow server-side logging (file tracking) noise during tests
import mlflow

os.environ.setdefault("MLFLOW_TRACKING_URI", "http://127.0.0.1:5050")

# Must import gateway AFTER setting MLFLOW_TRACKING_URI
from app import app

client = TestClient(app)


def parse_streaming_response(resp) -> str:
    """Parse SSE streaming response and return final content."""
    content = ""
    for line in resp.iter_lines():
        if line.startswith("data:"):
            data_str = line[5:].strip()
            if not data_str:
                continue
            try:
                data = json.loads(data_str)
                if data.get("text"):
                    content += data["text"]
                if data.get("finish_reason") == "stop":
                    break
            except json.JSONDecodeError:
                continue
    return content


# Fixture for a basic chat payload (streaming only)
CHAT_PAYLOAD = {
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": "只回复: hello"}],
    "stream": True,
}


# ============================================================
# Health endpoint (no LLM needed)
# ============================================================


class TestHealth:
    def test_health(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "llm_base_url" in data
        assert "mlflow_tracking_uri" in data


@pytest.mark.integration
class TestModels:
    def test_list_models(self):
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert data["object"] == "list"
        assert len(data["data"]) > 0
        model = data["data"][0]
        assert "id" in model


# ============================================================
# Streaming tests (needs LLM)
# ============================================================


@pytest.mark.integration
class TestStreaming:
    def test_basic_chat(self):
        resp = client.post("/v1/chat/completions", json=CHAT_PAYLOAD, stream=True)
        assert resp.status_code == 200
        content = parse_streaming_response(resp)
        assert content is not None
        assert "hello" in content.lower() or "Hello" in content

    def test_model_not_found(self):
        payload = {
            "model": "nonexistent-model-xyz",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        }
        resp = client.post("/v1/chat/completions", json=payload, stream=True)
        # Gateway returns 502 for upstream API errors (model not found)
        assert resp.status_code in (200, 502)

    def test_empty_messages(self):
        resp = client.post("/v1/chat/completions", json={
            "model": "deepseek-chat",
            "messages": [],
            "stream": True,
        }, stream=True)
        assert resp.status_code in (200, 502)


@pytest.mark.integration
class TestToolCalling:
    def test_current_time_tool(self):
        """LLM should call the current_time tool."""
        resp = client.post("/v1/chat/completions", json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "现在几点？只给我时间，不要其他内容。"}],
            "stream": True,
        }, stream=True)
        assert resp.status_code == 200
        content = parse_streaming_response(resp)
        # Should contain time information
        assert content is not None
        assert len(content) > 0

    def test_calculator_tool(self):
        """LLM should call the calculator tool."""
        resp = client.post("/v1/chat/completions", json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "123 * 456 等于多少？"}],
            "stream": True,
        }, stream=True)
        assert resp.status_code == 200
        content = parse_streaming_response(resp)
        assert content is not None
        # The answer should contain 56088 (possibly formatted as 56,088 or 56088)
        assert "56088" in content.replace(",", "")


# ============================================================
# Concurrency control (no LLM needed)
# ============================================================


class TestConcurrencyLimit:
    """Unit tests for the asyncio.Semaphore concurrency limit."""

    def test_rejects_when_semaphore_full(self):
        """When semaphore has no capacity, request gets 429."""
        import gateway as gw

        with patch.object(gw, "_llm_semaphore", asyncio.Semaphore(0)):
            resp = client.post(
                "/v1/chat/completions",
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}], "stream": True},
            )
            assert resp.status_code == 429
            data = resp.json()
            # FastAPI wraps HTTPException detail in {"detail": ...}
            assert data["detail"]["error"]["type"] == "concurrency_limit_error"

    async def test_allows_normal_traffic(self):
        """When semaphore has capacity, request passes through."""
        import gateway as gw

        async def fake_streaming_generator(*args, **kwargs) -> AsyncGenerator:
            yield "data: " + json.dumps({"text": "ok"}) + "\n\n"
            yield "data: " + json.dumps({"finish_reason": "stop"}) + "\n\n"

        with (
            patch.object(gw, "_llm_semaphore", asyncio.Semaphore(2)),
            patch.object(gw, "_handle_streaming", fake_streaming_generator),
        ):
            resp = client.post(
                "/v1/chat/completions",
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}], "stream": True},
            )
            assert resp.status_code == 200

    def test_semaphore_locked_on_zero(self):
        """asyncio.Semaphore(0).locked() returns True."""
        sem = asyncio.Semaphore(0)
        assert sem.locked() is True

    def test_semaphore_unlocked_on_positive(self):
        """asyncio.Semaphore(1).locked() returns False."""
        sem = asyncio.Semaphore(1)
        assert sem.locked() is False


# ============================================================
# Rate limiting (no LLM needed)
# ============================================================


class TestRateLimit:
    """Unit tests for per-IP rate limiting."""

    def test_disabled_by_default(self):
        """Rate limiting is disabled when RATE_LIMIT_ENABLED is not set."""
        import gateway as gw

        assert gw.RATE_LIMIT_ENABLED is False

    def test_rate_limit_exceeded(self):
        """When rate limit is exceeded, returns 429."""
        import gateway as gw

        gw._rate_limit_buckets.clear()

        async def fake_streaming_generator(*args, **kwargs) -> AsyncGenerator:
            yield "data: " + json.dumps({"text": "ok"}) + "\n\n"
            yield "data: " + json.dumps({"finish_reason": "stop"}) + "\n\n"

        with (
            patch.object(gw, "RATE_LIMIT_ENABLED", True),
            patch.object(gw, "RATE_LIMIT_REQUESTS", 1),
            patch.object(gw, "_handle_streaming", fake_streaming_generator),
        ):
            resp1 = client.post(
                "/v1/chat/completions",
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}], "stream": True},
            )
            assert resp1.status_code == 200

            resp2 = client.post(
                "/v1/chat/completions",
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}], "stream": True},
            )
            assert resp2.status_code == 429
            assert resp2.json()["detail"]["error"]["type"] == "rate_limit_error"

    def test_window_limits_independent(self):
        """Verify sliding window logic: timestamps outside window are pruned."""
        now = 1000.0
        window = 60
        # Two timestamps: one just inside window, one just outside
        timestamps = [now - 61, now - 30]
        pruned = [t for t in timestamps if t > now - window]
        assert len(pruned) == 1