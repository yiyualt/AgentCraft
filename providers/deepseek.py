"""DeepSeek provider implementation."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator

import httpx

from .base import Provider

logger = logging.getLogger(__name__)


class DeepSeekProvider(Provider):
    """DeepSeek API provider."""

    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
    DEFAULT_MODEL = "deepseek-chat"

    SUPPORTED_MODELS = [
        "deepseek-chat",
        "deepseek-coder",
        "deepseek-reasoner",
    ]

    CAPABILITIES = ["streaming", "tools"]

    def __init__(self, api_key: str, base_url: str | None = None):
        super().__init__(api_key, base_url)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(300.0, connect=30.0),
        )

    @property
    def name(self) -> str:
        return "DeepSeek"

    @property
    def provider_type(self) -> str:
        return "deepseek"

    @property
    def default_base_url(self) -> str:
        return self.DEFAULT_BASE_URL

    @property
    def default_model(self) -> str:
        return self.DEFAULT_MODEL

    @property
    def supported_models(self) -> list[str]:
        return self.SUPPORTED_MODELS

    @property
    def capabilities(self) -> list[str]:
        return self.CAPABILITIES

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Non-streaming completion."""
        model = model or self.default_model
        start_time = time.time()

        payload = {
            "model": model,
            "messages": messages,
            **kwargs,
        }

        try:
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            result = response.json()

            latency_ms = (time.time() - start_time) * 1000
            tokens = result.get("usage", {}).get("total_tokens", 0)
            self.record_success(tokens, latency_ms)

            return result

        except Exception as e:
            self.record_failure()
            logger.error(f"[DeepSeek] Completion failed: {e}")
            raise

    async def stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs,
    ) -> AsyncIterator[dict[str, Any]]:
        """Streaming completion with minimal buffering."""
        model = model or self.default_model
        start_time = time.time()

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            **kwargs,
        }

        total_tokens = 0

        try:
            # CRITICAL: Use stream() method for true streaming
            # post() waits for full response before returning
            async with self._client.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()

                buf = ""
                async for chunk in response.aiter_bytes():
                    # Decode bytes to text incrementally
                    buf += chunk.decode("utf-8", errors="ignore")

                    # Process complete lines immediately
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()

                        if not line:
                            continue
                        if not line.startswith("data: "):
                            continue

                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            parsed = json.loads(data)
                            total_tokens += parsed.get("usage", {}).get("total_tokens", 0)
                            yield parsed
                        except json.JSONDecodeError:
                            continue

            latency_ms = (time.time() - start_time) * 1000
            self.record_success(total_tokens, latency_ms)

        except Exception as e:
            self.record_failure()
            logger.error(f"[DeepSeek] Stream failed: {e}")
            raise

    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()