"""Model catalog for managing LLM models and capabilities."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Model metadata and capabilities."""
    name: str
    provider_type: str
    aliases: list[str] = field(default_factory=list)
    context_window: int = 128000
    max_output_tokens: int = 4096
    capabilities: list[str] = field(default_factory=list)  # "vision", "streaming", "tools", "reasoning"
    pricing_input: float = 0.0  # Per million tokens
    pricing_output: float = 0.0  # Per million tokens
    default_temperature: float = 0.7
    supports_system_prompt: bool = True
    deprecated: bool = False
    replacement: str | None = None  # Suggested replacement if deprecated


# Default model definitions
DEFAULT_MODELS: dict[str, ModelInfo] = {
    # DeepSeek models
    "deepseek-chat": ModelInfo(
        name="deepseek-chat",
        provider_type="deepseek",
        aliases=["deepseek"],
        context_window=128000,
        max_output_tokens=4096,
        capabilities=["streaming", "tools"],
        pricing_input=0.14,
        pricing_output=0.28,
    ),
    "deepseek-coder": ModelInfo(
        name="deepseek-coder",
        provider_type="deepseek",
        aliases=["deepseek-coding"],
        context_window=128000,
        max_output_tokens=4096,
        capabilities=["streaming", "tools"],
        pricing_input=0.14,
        pricing_output=0.28,
    ),
    "deepseek-reasoner": ModelInfo(
        name="deepseek-reasoner",
        provider_type="deepseek",
        aliases=["deepseek-r1"],
        context_window=128000,
        max_output_tokens=4096,
        capabilities=["streaming", "reasoning"],
        pricing_input=0.55,
        pricing_output=2.19,
    ),

    # Anthropic models
    "claude-opus-4-7": ModelInfo(
        name="claude-opus-4-7",
        provider_type="anthropic",
        aliases=["claude-opus", "opus"],
        context_window=200000,
        max_output_tokens=16384,
        capabilities=["streaming", "tools", "vision"],
        pricing_input=15.0,
        pricing_output=75.0,
    ),
    "claude-sonnet-4-6": ModelInfo(
        name="claude-sonnet-4-6",
        provider_type="anthropic",
        aliases=["claude-sonnet", "sonnet"],
        context_window=200000,
        max_output_tokens=8192,
        capabilities=["streaming", "tools", "vision"],
        pricing_input=3.0,
        pricing_output=15.0,
    ),
    "claude-haiku-4-5-20251001": ModelInfo(
        name="claude-haiku-4-5-20251001",
        provider_type="anthropic",
        aliases=["claude-haiku", "haiku"],
        context_window=200000,
        max_output_tokens=8192,
        capabilities=["streaming", "tools", "vision"],
        pricing_input=0.8,
        pricing_output=4.0,
    ),

    # OpenAI models
    "gpt-4o": ModelInfo(
        name="gpt-4o",
        provider_type="openai",
        aliases=["gpt-4-omni"],
        context_window=128000,
        max_output_tokens=4096,
        capabilities=["streaming", "tools", "vision"],
        pricing_input=5.0,
        pricing_output=15.0,
    ),
    "gpt-4o-mini": ModelInfo(
        name="gpt-4o-mini",
        provider_type="openai",
        aliases=["gpt-4-mini"],
        context_window=128000,
        max_output_tokens=4096,
        capabilities=["streaming", "tools", "vision"],
        pricing_input=0.15,
        pricing_output=0.6,
    ),
    "o1": ModelInfo(
        name="o1",
        provider_type="openai",
        aliases=["o1-preview"],
        context_window=200000,
        max_output_tokens=100000,
        capabilities=["reasoning"],
        pricing_input=15.0,
        pricing_output=60.0,
    ),
    "o1-mini": ModelInfo(
        name="o1-mini",
        provider_type="openai",
        aliases=["o1-mini"],
        context_window=128000,
        max_output_tokens=65536,
        capabilities=["reasoning"],
        pricing_input=3.0,
        pricing_output=12.0,
    ),
}


@dataclass
class ModelCache:
    """Cache for model context windows detected from API responses."""
    model: str
    context_window: int
    detected_at: float
    source: str  # "api", "config", "default"


class ModelCatalog:
    """Catalog for managing LLM models."""

    CACHE_PATH = Path("~/.agentcraft/model-cache.json")

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = Path(config_path or "~/.agentcraft/models.yaml").expanduser()
        self._models: dict[str, ModelInfo] = {}
        self._cache: dict[str, ModelCache] = {}
        self._load()
        self._load_cache()

    def _load(self):
        """Load model definitions from config."""
        # Start with defaults
        self._models = dict(DEFAULT_MODELS)

        # Load user config if exists
        if self.config_path.exists():
            try:
                data = yaml.safe_load(self.config_path.read_text())
                if data and "models" in data:
                    for name, cfg in data["models"].items():
                        self._models[name] = ModelInfo(
                            name=name,
                            provider_type=cfg.get("provider_type", "unknown"),
                            aliases=cfg.get("aliases", []),
                            context_window=cfg.get("context_window", 128000),
                            max_output_tokens=cfg.get("max_output_tokens", 4096),
                            capabilities=cfg.get("capabilities", []),
                            pricing_input=cfg.get("pricing_input", 0.0),
                            pricing_output=cfg.get("pricing_output", 0.0),
                        )
                logger.info(f"[ModelCatalog] Loaded {len(self._models)} models")
            except Exception as e:
                logger.error(f"[ModelCatalog] Failed to load config: {e}")

    def _load_cache(self):
        """Load context window cache."""
        cache_path = self.CACHE_PATH.expanduser()
        if cache_path.exists():
            try:
                data = json.loads(cache_path.read_text())
                for model, cached in data.get("cache", {}).items():
                    self._cache[model] = ModelCache(
                        model=model,
                        context_window=cached["context_window"],
                        detected_at=cached["detected_at"],
                        source=cached["source"],
                    )
            except Exception as e:
                logger.warning(f"[ModelCatalog] Cache load failed: {e}")

    def _save_cache(self):
        """Save context window cache."""
        cache_path = self.CACHE_PATH.expanduser()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "cache": {
                m.model: {
                    "context_window": m.context_window,
                    "detected_at": m.detected_at,
                    "source": m.source,
                }
                for m in self._cache.values()
            }
        }
        cache_path.write_text(json.dumps(data, indent=2))

    def get_model(self, name: str) -> ModelInfo | None:
        """Get model by name or alias."""
        # Direct lookup
        if name in self._models:
            return self._models[name]

        # Alias lookup
        for model in self._models.values():
            if name in model.aliases:
                return model

        return None

    def get_context_window(self, model_name: str) -> int:
        """Get context window for a model (uses cache if available)."""
        # Check cache first
        if model_name in self._cache:
            return self._cache[model_name].context_window

        # Check model definition
        model = self.get_model(model_name)
        if model:
            return model.context_window

        # Default fallback
        return 128000

    def update_context_window_from_api(
        self,
        model_name: str,
        response: dict[str, Any],
    ):
        """Update context window from API response.

        Some APIs return context window info in response headers or body.
        """
        # OpenAI/DeepSeek: sometimes includes max_tokens requested
        # Anthropic: sometimes includes input_tokens which hints at usage

        # For now, just log that we detected usage
        usage = response.get("usage", {})
        if usage:
            logger.debug(
                f"[ModelCatalog] Model {model_name} used "
                f"{usage.get('prompt_tokens', 0)} input, "
                f"{usage.get('completion_tokens', 0)} output tokens"
            )

    def detect_context_window(self, model_name: str) -> int:
        """Attempt to detect context window from model name.

        Common patterns:
        - "4k" → 4096
        - "8k" → 8192
        - "32k" → 32768
        - "128k" → 128000
        """
        model_lower = model_name.lower()

        # Check known patterns
        if "128k" in model_lower:
            return 128000
        if "200k" in model_lower:
            return 200000
        if "32k" in model_lower:
            return 32768
        if "8k" in model_lower:
            return 8192
        if "4k" in model_lower:
            return 4096

        # Default
        return 128000

    def list_models(self) -> list[ModelInfo]:
        """List all available models."""
        return list(self._models.values())

    def list_models_by_provider(self, provider_type: str) -> list[ModelInfo]:
        """List models for a specific provider."""
        return [m for m in self._models.values() if m.provider_type == provider_type]

    def get_models_by_capability(self, capability: str) -> list[ModelInfo]:
        """Get models that support a capability."""
        return [m for m in self._models.values() if capability in m.capabilities]

    def supports_capability(self, model_name: str, capability: str) -> bool:
        """Check if a model supports a capability."""
        model = self.get_model(model_name)
        if model:
            return capability in model.capabilities
        return False

    def select_model(
        self,
        name: str | None = None,
        provider_type: str | None = None,
        capability: str | None = None,
    ) -> ModelInfo | None:
        """Select model by various criteria."""
        # By exact name
        if name:
            return self.get_model(name)

        # By provider + capability
        if provider_type and capability:
            models = self.list_models_by_provider(provider_type)
            for m in models:
                if capability in m.capabilities:
                    return m
            return models[0] if models else None

        # By capability only (return first)
        if capability:
            models = self.get_models_by_capability(capability)
            return models[0] if models else None

        # By provider only (return first)
        if provider_type:
            models = self.list_models_by_provider(provider_type)
            return models[0] if models else None

        # Default: first model
        return self._models.get("deepseek-chat")

    def get_fallback_models(
        self,
        model_name: str,
        within_provider: bool = True,
    ) -> list[str]:
        """Get fallback models for a given model.

        Args:
            model_name: Current model
            within_provider: If True, only fallback within same provider

        Returns:
            List of fallback model names
        """
        model = self.get_model(model_name)
        if not model:
            return []

        if within_provider:
            # Fallback within same provider
            models = self.list_models_by_provider(model.provider_type)
            return [m.name for m in models if m.name != model_name]

        # Cross-provider fallback (by priority)
        return [
            "deepseek-chat",
            "claude-sonnet-4-6",
            "gpt-4o-mini",
        ]


# Global catalog instance
_catalog: ModelCatalog | None = None


def get_catalog() -> ModelCatalog | None:
    """Get global model catalog."""
    return _catalog


def init_catalog(config_path: str | Path | None = None) -> ModelCatalog:
    """Initialize global model catalog."""
    global _catalog
    _catalog = ModelCatalog(config_path)
    return _catalog