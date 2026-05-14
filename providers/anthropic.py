"""Anthropic provider implementation."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator

import httpx

from .base import Provider

logger = logging.getLogger(__name__)


class AnthropicProvider(Provider):
    """Anthropic Claude API provider."""

    DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
    DEFAULT_MODEL = "claude-sonnet-4-6"

    SUPPORTED_MODELS = [
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ]

    CAPABILITIES = ["streaming", "tools", "vision"]

    def __init__(self, api_key: str, base_url: str | None = None):
        super().__init__(api_key, base_url)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(300.0, connect=30.0),
        )

    @property
    def name(self) -> str:
        return "Anthropic"

    @property
    def provider_type(self) -> str:
        return "anthropic"

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

    def _convert_messages_to_anthropic(
        self, messages: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Convert OpenAI-format messages to Anthropic format.

        Returns:
            (anthropic_messages, system_prompt)
        """
        anthropic_messages = []
        system_prompt = None

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            if role == "system":
                system_prompt = content
            elif role in ("user", "assistant"):
                anthropic_messages.append({
                    "role": role,
                    "content": content,
                })

        return anthropic_messages, system_prompt

    def _convert_response_to_openai(self, response: dict[str, Any]) -> dict[str, Any]:
        """Convert Anthropic response to OpenAI format."""
        content = response.get("content", [])
        text_content = ""
        for block in content:
            if block.get("type") == "text":
                text_content += block.get("text", "")

        return {
            "id": response.get("id", ""),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": response.get("model", self.default_model),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": text_content,
                },
                "finish_reason": response.get("stop_reason", "stop"),
            }],
            "usage": {
                "prompt_tokens": response.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": response.get("usage", {}).get("output_tokens", 0),
                "total_tokens": response.get("usage", {}).get("input_tokens", 0)
                    + response.get("usage", {}).get("output_tokens", 0),
            },
        }

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Non-streaming completion."""
        model = model or self.default_model
        start_time = time.time()

        anthropic_messages, system_prompt = self._convert_messages_to_anthropic(messages)

        payload = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
        }

        if system_prompt:
            payload["system"] = system_prompt

        if "tools" in kwargs:
            payload["tools"] = self._convert_tools_to_anthropic(kwargs["tools"])

        try:
            response = await self._client.post("/messages", json=payload)
            response.raise_for_status()
            result = response.json()

            latency_ms = (time.time() - start_time) * 1000
            tokens = result.get("usage", {}).get("input_tokens", 0) + \
                     result.get("usage", {}).get("output_tokens", 0)
            self.record_success(tokens, latency_ms)

            return self._convert_response_to_openai(result)

        except Exception as e:
            self.record_failure()
            logger.error(f"[Anthropic] Completion failed: {e}")
            raise

    async def stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs,
    ) -> AsyncIterator[dict[str, Any]]:
        """Streaming completion."""
        model = model or self.default_model
        start_time = time.time()

        anthropic_messages, system_prompt = self._convert_messages_to_anthropic(messages)

        payload = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "stream": True,
        }

        if system_prompt:
            payload["system"] = system_prompt

        total_tokens = 0

        try:
            response = await self._client.post("/messages", json=payload)
            response.raise_for_status()

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    try:
                        event = json.loads(data)
                        event_type = event.get("type")

                        if event_type == "content_block_delta":
                            delta = event.get("delta", {})
                            text = delta.get("text", "")
                            yield {
                                "id": event.get("id", ""),
                                "object": "chat.completion.chunk",
                                "model": model,
                                "choices": [{
                                    "index": 0,
                                    "delta": {"content": text},
                                    "finish_reason": None,
                                }],
                            }
                        elif event_type == "message_stop":
                            yield {
                                "id": "",
                                "object": "chat.completion.chunk",
                                "model": model,
                                "choices": [{
                                    "index": 0,
                                    "delta": {},
                                    "finish_reason": "stop",
                                }],
                            }
                            break
                        elif event_type == "message_start":
                            total_tokens = event.get("message", {}).get("usage", {}).get("input_tokens", 0)

                    except json.JSONDecodeError:
                        continue

            latency_ms = (time.time() - start_time) * 1000
            self.record_success(total_tokens, latency_ms)

        except Exception as e:
            self.record_failure()
            logger.error(f"[Anthropic] Stream failed: {e}")
            raise

    def _convert_tools_to_anthropic(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI tools to Anthropic format."""
        anthropic_tools = []
        for tool in tools:
            func = tool.get("function", {})
            anthropic_tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object"}),
            })
        return anthropic_tools

    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()