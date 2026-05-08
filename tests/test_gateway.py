"""Integration tests for gateway.py.

Requires the LLM (Ollama) to be running.
All tests are marked @pytest.mark.integration and are skipped by default:
    uv run pytest                          # skips integration
    uv run pytest -m integration           # runs integration tests

These tests log to MLFLOW_TRACKING_URI (default: http://127.0.0.1:5050).
Make sure the MLflow server is running before running integration tests.
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

# Suppress mlflow server-side logging (file tracking) noise during tests
import mlflow

os.environ.setdefault("MLFLOW_TRACKING_URI", "http://127.0.0.1:5050")

# Must import gateway AFTER setting MLFLOW_TRACKING_URI
from gateway import app

client = TestClient(app)

# Fixture for a basic chat payload
CHAT_PAYLOAD = {
    "model": "qwen3:8b",
    "messages": [{"role": "user", "content": "只回复: hello"}],
    "stream": False,
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
        assert "ollama_base_url" in data
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
        assert model["owned_by"] == "ollama"


# ============================================================
# Non-streaming (needs LLM)
# ============================================================


@pytest.mark.integration
class TestNonStreaming:
    def test_basic_chat(self):
        resp = client.post("/v1/chat/completions", json=CHAT_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert "choices" in data
        assert len(data["choices"]) > 0
        content = data["choices"][0]["message"]["content"]
        assert content is not None
        assert "hello" in content.lower() or "Hello" in content

    def test_model_not_found(self):
        payload = {
            "model": "nonexistent-model-xyz",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        }
        resp = client.post("/v1/chat/completions", json=payload)
        # The gateway should return an error gracefully, not crash
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data or "choices" in data

    def test_empty_messages(self):
        resp = client.post("/v1/chat/completions", json={
            "model": "qwen3:8b",
            "messages": [],
            "stream": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data or "choices" in data


@pytest.mark.integration
class TestToolCalling:
    def test_current_time_tool(self):
        """LLM should call the current_time tool."""
        resp = client.post("/v1/chat/completions", json={
            "model": "qwen3:8b",
            "messages": [{"role": "user", "content": "现在几点？只给我时间，不要其他内容。"}],
            "stream": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        # Should contain time information
        assert content is not None
        assert len(content) > 0

    def test_calculator_tool(self):
        """LLM should call the calculator tool."""
        resp = client.post("/v1/chat/completions", json={
            "model": "qwen3:8b",
            "messages": [{"role": "user", "content": "123 * 456 等于多少？"}],
            "stream": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        assert content is not None
        # The answer should contain 56088 (possibly formatted as 56,088 or 56088)
        assert "56088" in content.replace(",", "")


@pytest.mark.integration
class TestStreaming:
    def test_basic_streaming(self):
        """Streaming should return SSE chunks ending with [DONE]."""
        payload = {
            "model": "qwen3:8b",
            "messages": [{"role": "user", "content": "只回复: hi"}],
            "stream": True,
        }
        with client.stream("POST", "/v1/chat/completions", json=payload) as resp:
            assert resp.status_code == 200
            chunks = []
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    chunks.append(line)

            assert len(chunks) >= 2  # at least one data chunk + [DONE]
            # Last chunk should be [DONE]
            assert chunks[-1] == "data: [DONE]"

            # First data chunk should be valid JSON
            first_data = json.loads(chunks[0][6:])  # strip "data: "
            assert "choices" in first_data
