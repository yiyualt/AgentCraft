"""Provider registry with fallback support."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .base import Provider, ProviderInfo, ProviderStatus
from .deepseek import DeepSeekProvider
from .anthropic import AnthropicProvider
from .openai import OpenAIProvider

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    """Configuration for a provider instance."""
    provider_type: str
    api_keys: list[str] = field(default_factory=list)
    base_url: str | None = None
    priority: int = 0  # Higher priority = tried first
    enabled: bool = True
    models: list[str] = field(default_factory=list)


class ProviderRegistry:
    """Registry for managing multiple LLM providers with fallback."""

    def __init__(self):
        self._providers: dict[str, Provider] = {}
        self._configs: dict[str, ProviderConfig] = {}
        self._fallback_order: list[str] = []  # Provider types in fallback order

    def register_provider(
        self,
        provider_type: str,
        api_key: str,
        base_url: str | None = None,
        priority: int = 0,
    ) -> Provider:
        """Register a provider instance.

        Args:
            provider_type: "deepseek", "anthropic", "openai"
            api_key: API key for this provider
            base_url: Optional custom base URL
            priority: Fallback priority (higher = tried first)

        Returns:
            Provider instance
        """
        provider = self._create_provider(provider_type, api_key, base_url)
        key = f"{provider_type}:{api_key[:8]}"
        self._providers[key] = provider
        self._configs[key] = ProviderConfig(
            provider_type=provider_type,
            api_keys=[api_key],
            base_url=base_url,
            priority=priority,
        )
        self._update_fallback_order()
        logger.info(f"[ProviderRegistry] Registered {provider_type} with priority {priority}")
        return provider

    def register_config(self, config: ProviderConfig) -> list[Provider]:
        """Register providers from a config (supports multiple API keys).

        Returns:
            List of provider instances (one per API key)
        """
        providers = []
        for api_key in config.api_keys:
            provider = self._create_provider(
                config.provider_type,
                api_key,
                config.base_url,
            )
            key = f"{config.provider_type}:{api_key[:8]}"
            self._providers[key] = provider
            self._configs[key] = config
            providers.append(provider)

        self._update_fallback_order()
        logger.info(
            f"[ProviderRegistry] Registered {config.provider_type} "
            f"with {len(config.api_keys)} keys, priority {config.priority}"
        )
        return providers

    def _create_provider(
        self,
        provider_type: str,
        api_key: str,
        base_url: str | None = None,
    ) -> Provider:
        """Create provider instance by type."""
        if provider_type == "deepseek":
            return DeepSeekProvider(api_key, base_url)
        elif provider_type == "anthropic":
            return AnthropicProvider(api_key, base_url)
        elif provider_type == "openai":
            return OpenAIProvider(api_key, base_url)
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")

    def _update_fallback_order(self):
        """Update fallback order based on priorities."""
        # Sort by priority (descending), then by provider type
        sorted_configs = sorted(
            self._configs.items(),
            key=lambda x: (-x[1].priority, x[1].provider_type),
        )
        # Get unique provider types in order
        seen = set()
        self._fallback_order = []
        for key, config in sorted_configs:
            if config.enabled and config.provider_type not in seen:
                seen.add(config.provider_type)
                self._fallback_order.append(config.provider_type)

    def get_provider(self, provider_type: str) -> Provider | None:
        """Get first available provider of given type."""
        for key, provider in self._providers.items():
            if provider.provider_type == provider_type and provider.is_available():
                return provider
        return None

    def get_provider_by_key(self, key: str) -> Provider | None:
        """Get provider by registration key."""
        return self._providers.get(key)

    def get_all_providers(self) -> list[Provider]:
        """Get all registered providers."""
        return list(self._providers.values())

    def get_available_providers(self) -> list[Provider]:
        """Get all available (non-failed) providers."""
        return [p for p in self._providers.values() if p.is_available()]

    def get_providers_by_type(self, provider_type: str) -> list[Provider]:
        """Get all providers of a specific type."""
        return [
            p for p in self._providers.values()
            if p.provider_type == provider_type
        ]

    def get_fallback_chain(self) -> list[Provider]:
        """Get providers in fallback order (available only)."""
        chain = []
        for provider_type in self._fallback_order:
            providers = self.get_providers_by_type(provider_type)
            # Get first available provider of this type
            for provider in providers:
                if provider.is_available():
                    chain.append(provider)
                    break
        return chain

    async def complete_with_fallback(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Complete with automatic fallback on failure.

        Tries providers in fallback order until one succeeds.
        """
        chain = self.get_fallback_chain()

        if not chain:
            raise RuntimeError("No available providers")

        last_error = None

        for provider in chain:
            try:
                logger.info(f"[ProviderRegistry] Trying {provider.name}")
                result = await provider.complete(messages, model, **kwargs)
                return result
            except Exception as e:
                last_error = e
                logger.warning(
                    f"[ProviderRegistry] {provider.name} failed: {e}, "
                    f"trying next provider"
                )
                continue

        raise RuntimeError(f"All providers failed. Last error: {last_error}")

    async def stream_with_fallback(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs,
    ) -> Any:
        """Stream with automatic fallback on failure."""
        chain = self.get_fallback_chain()

        if not chain:
            raise RuntimeError("No available providers")

        # For streaming, we try first provider only
        # Fallback during streaming is complex and may lose context
        provider = chain[0]
        logger.info(f"[ProviderRegistry] Streaming from {provider.name}")
        return provider.stream(messages, model, **kwargs)

    async def stream_iterator(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs,
    ) -> Any:
        """Get streaming iterator from provider for direct consumption.

        Returns AsyncIterator[dict] that can be directly iterated
        in streaming response handlers.

        Unlike stream_with_fallback, this is designed for the new
        LLMQueue architecture where streaming happens after semaphore
        acquisition.
        """
        chain = self.get_fallback_chain()

        if not chain:
            raise RuntimeError("No available providers")

        provider = chain[0]
        logger.info(f"[ProviderRegistry] stream_iterator from {provider.name}")

        # Return the async iterator directly (provider.stream is async generator)
        return provider.stream(messages, model, **kwargs)

    def get_provider_info(self) -> list[ProviderInfo]:
        """Get info for all registered providers."""
        return [p.get_info() for p in self._providers.values()]

    def get_status_summary(self) -> dict[str, Any]:
        """Get status summary for all providers."""
        summary = {}
        for provider_type in self._fallback_order:
            providers = self.get_providers_by_type(provider_type)
            available = sum(1 for p in providers if p.is_available())
            total = len(providers)
            summary[provider_type] = {
                "available": available,
                "total": total,
                "status": "ok" if available > 0 else "failed",
            }
        return summary

    async def close_all(self):
        """Close all provider HTTP clients."""
        for provider in self._providers.values():
            if hasattr(provider, "close"):
                await provider.close()


# Global registry instance
_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry | None:
    """Get global provider registry."""
    return _registry


def init_registry() -> ProviderRegistry:
    """Initialize global provider registry."""
    global _registry
    _registry = ProviderRegistry()
    return _registry


def register_default_providers(
    deepseek_key: str | None = None,
    anthropic_key: str | None = None,
    openai_key: str | None = None,
) -> ProviderRegistry:
    """Register default providers from environment variables.

    Priority: DeepSeek (100) > Anthropic (50) > OpenAI (0)
    """
    import os

    registry = init_registry()

    # DeepSeek (highest priority)
    deepseek_key = deepseek_key or os.environ.get("DEEPSEEK_API_KEY")
    if deepseek_key:
        registry.register_provider("deepseek", deepseek_key, priority=100)

    # Anthropic
    anthropic_key = anthropic_key or os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        registry.register_provider("anthropic", anthropic_key, priority=50)

    # OpenAI (lowest priority)
    openai_key = openai_key or os.environ.get("OPENAI_API_KEY")
    if openai_key:
        registry.register_provider("openai", openai_key, priority=0)

    return registry