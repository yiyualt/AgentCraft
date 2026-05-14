"""Provider base class and registry for LLM API abstraction."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


class ProviderStatus(Enum):
    """Provider health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Partial failures
    FAILED = "failed"      # Complete failure
    UNKNOWN = "unknown"


@dataclass
class ProviderMetrics:
    """Provider performance metrics."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_tokens: int = 0
    avg_latency_ms: float = 0.0
    last_success_time: float | None = None
    last_failure_time: float | None = None
    consecutive_failures: int = 0


@dataclass
class ProviderInfo:
    """Provider metadata."""
    name: str
    provider_type: str  # "deepseek", "anthropic", "openai"
    base_url: str
    models: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)  # "vision", "streaming", "tools"
    default_model: str = ""
    max_context_window: int = 128000
    status: ProviderStatus = ProviderStatus.UNKNOWN
    metrics: ProviderMetrics = field(default_factory=ProviderMetrics)


class Provider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, api_key: str, base_url: str | None = None):
        self._api_key = api_key
        self._base_url = base_url or self.default_base_url
        self._metrics = ProviderMetrics()

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        ...

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """Provider type identifier."""
        ...

    @property
    @abstractmethod
    def default_base_url(self) -> str:
        """Default API base URL."""
        ...

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model for this provider."""
        ...

    @property
    @abstractmethod
    def supported_models(self) -> list[str]:
        """List of supported model names/aliases."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> list[str]:
        """Provider capabilities: vision, streaming, tools, etc."""
        ...

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Non-streaming completion.

        Args:
            messages: OpenAI-format messages
            model: Model name (uses default if None)
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            OpenAI-format response with choices, usage, etc.
        """
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs,
    ) -> AsyncIterator[dict[str, Any]]:
        """Streaming completion.

        Yields:
            OpenAI-format stream chunks
        """
        ...

    def get_info(self) -> ProviderInfo:
        """Get provider metadata."""
        return ProviderInfo(
            name=self.name,
            provider_type=self.provider_type,
            base_url=self._base_url,
            models=self.supported_models,
            capabilities=self.capabilities,
            default_model=self.default_model,
            status=self._get_status(),
            metrics=self._metrics,
        )

    def _get_status(self) -> ProviderStatus:
        """Determine provider status from metrics."""
        if self._metrics.consecutive_failures >= 3:
            return ProviderStatus.FAILED
        if self._metrics.consecutive_failures >= 1:
            return ProviderStatus.DEGRADED
        if self._metrics.total_requests > 0:
            return ProviderStatus.HEALTHY
        return ProviderStatus.UNKNOWN

    def record_success(self, tokens: int = 0, latency_ms: float = 0.0):
        """Record successful request."""
        import time
        self._metrics.total_requests += 1
        self._metrics.successful_requests += 1
        self._metrics.total_tokens += tokens
        self._metrics.last_success_time = time.time()
        self._metrics.consecutive_failures = 0
        # Update average latency
        n = self._metrics.successful_requests
        self._metrics.avg_latency_ms = (
            (self._metrics.avg_latency_ms * (n - 1) + latency_ms) / n
        )

    def record_failure(self):
        """Record failed request."""
        import time
        self._metrics.total_requests += 1
        self._metrics.failed_requests += 1
        self._metrics.last_failure_time = time.time()
        self._metrics.consecutive_failures += 1

    def is_available(self) -> bool:
        """Check if provider is available for requests."""
        return self._get_status() != ProviderStatus.FAILED

    def supports_capability(self, capability: str) -> bool:
        """Check if provider supports a capability."""
        return capability in self.capabilities()