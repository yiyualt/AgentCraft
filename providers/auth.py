"""Auth profile management for multi-key rotation."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class KeyProfile:
    """Single API key profile with failure tracking."""
    key: str
    provider_type: str
    name: str = ""  # Human-readable name
    priority: int = 0
    enabled: bool = True
    failure_count: int = 0
    last_failure_time: float | None = None
    last_success_time: float | None = None
    cooldown_until: float | None = None  # Timestamp when key becomes available again

    def is_available(self) -> bool:
        """Check if key is available for use."""
        if not self.enabled:
            return False
        if self.cooldown_until and time.time() < self.cooldown_until:
            return False
        return True

    def record_failure(self, cooldown_seconds: int = 60):
        """Record failure and set cooldown."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        # Exponential cooldown: 60s, 120s, 240s...
        cooldown = cooldown_seconds * (2 ** min(self.failure_count - 1, 5))
        self.cooldown_until = time.time() + cooldown
        logger.warning(
            f"[AuthProfile] Key '{self.name}' failed (count={self.failure_count}), "
            f"cooldown for {cooldown}s"
        )

    def record_success(self):
        """Record success and reset failure count."""
        self.failure_count = 0
        self.last_success_time = time.time()
        self.cooldown_until = None

    def reset_cooldown(self):
        """Manually reset cooldown."""
        self.cooldown_until = None
        self.failure_count = 0


@dataclass
class ProviderAuthProfile:
    """Auth profile for a single provider with multiple keys."""
    provider_type: str
    keys: list[KeyProfile] = field(default_factory=list)
    priority: int = 0  # Provider priority (higher = preferred)
    cooldown_seconds: int = 60
    max_failures_before_disable: int = 10

    def get_available_keys(self) -> list[KeyProfile]:
        """Get all available keys sorted by priority."""
        available = [k for k in self.keys if k.is_available()]
        # Sort by priority (descending)
        return sorted(available, key=lambda k: -k.priority)

    def get_next_key(self) -> KeyProfile | None:
        """Get next available key."""
        available = self.get_available_keys()
        return available[0] if available else None

    def rotate_key(self, current_key: KeyProfile) -> KeyProfile | None:
        """Rotate to next available key after failure."""
        current_key.record_failure(self.cooldown_seconds)

        # Check if key should be disabled
        if current_key.failure_count >= self.max_failures_before_disable:
            current_key.enabled = False
            logger.error(
                f"[AuthProfile] Key '{current_key.name}' disabled after "
                f"{current_key.failure_count} failures"
            )

        return self.get_next_key()

    def add_key(self, key: str, name: str = "", priority: int = 0):
        """Add new key to profile."""
        self.keys.append(KeyProfile(
            key=key,
            provider_type=self.provider_type,
            name=name or f"key-{len(self.keys) + 1}",
            priority=priority,
        ))

    def get_status(self) -> dict[str, Any]:
        """Get status summary."""
        available = len(self.get_available_keys())
        total = len(self.keys)
        return {
            "provider_type": self.provider_type,
            "total_keys": total,
            "available_keys": available,
            "status": "ok" if available > 0 else "exhausted",
            "keys": [
                {
                    "name": k.name,
                    "available": k.is_available(),
                    "failure_count": k.failure_count,
                }
                for k in self.keys
            ],
        }


class AuthProfileStore:
    """Store for managing auth profiles across providers."""

    DEFAULT_CONFIG_PATH = Path("~/.agentcraft/providers.yaml")

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = Path(config_path or self.DEFAULT_CONFIG_PATH).expanduser()
        self._profiles: dict[str, ProviderAuthProfile] = {}
        self._load()

    def _load(self):
        """Load auth profiles from YAML config."""
        if not self.config_path.exists():
            logger.info(f"[AuthProfileStore] Config not found: {self.config_path}")
            return

        try:
            data = yaml.safe_load(self.config_path.read_text())
            if not data:
                return

            for provider_type, cfg in data.get("providers", {}).items():
                keys_cfg = cfg.get("keys", [])
                keys = []
                for i, key_cfg in enumerate(keys_cfg):
                    if isinstance(key_cfg, str):
                        # Simple key string
                        keys.append(KeyProfile(
                            key=key_cfg,
                            provider_type=provider_type,
                            name=f"key-{i + 1}",
                            priority=cfg.get("priority", 0),
                        ))
                    elif isinstance(key_cfg, dict):
                        # Full key config
                        keys.append(KeyProfile(
                            key=key_cfg.get("key", ""),
                            provider_type=provider_type,
                            name=key_cfg.get("name", f"key-{i + 1}"),
                            priority=key_cfg.get("priority", cfg.get("priority", 0)),
                            enabled=key_cfg.get("enabled", True),
                        ))

                self._profiles[provider_type] = ProviderAuthProfile(
                    provider_type=provider_type,
                    keys=keys,
                    priority=cfg.get("priority", 0),
                    cooldown_seconds=cfg.get("cooldown_seconds", 60),
                    max_failures_before_disable=cfg.get("max_failures_before_disable", 10),
                )

            logger.info(f"[AuthProfileStore] Loaded {len(self._profiles)} provider profiles")

        except Exception as e:
            logger.error(f"[AuthProfileStore] Failed to load config: {e}")

    def get_profile(self, provider_type: str) -> ProviderAuthProfile | None:
        """Get auth profile for a provider."""
        return self._profiles.get(provider_type)

    def get_next_key(self, provider_type: str) -> KeyProfile | None:
        """Get next available key for a provider."""
        profile = self.get_profile(provider_type)
        if profile:
            return profile.get_next_key()
        return None

    def rotate_key(self, provider_type: str, current_key: KeyProfile) -> KeyProfile | None:
        """Rotate key after failure."""
        profile = self.get_profile(provider_type)
        if profile:
            return profile.rotate_key(current_key)
        return None

    def record_success(self, provider_type: str, key: str):
        """Record successful use of a key."""
        profile = self.get_profile(provider_type)
        if profile:
            for k in profile.keys:
                if k.key == key:
                    k.record_success()
                    break

    def get_all_profiles(self) -> list[ProviderAuthProfile]:
        """Get all provider profiles."""
        return list(self._profiles.values())

    def get_status_summary(self) -> dict[str, Any]:
        """Get status summary for all providers."""
        summary = {}
        for provider_type, profile in self._profiles.items():
            summary[provider_type] = profile.get_status()
        return summary

    def reset_all_cooldowns(self):
        """Reset cooldowns for all keys."""
        for profile in self._profiles.values():
            for key in profile.keys:
                key.reset_cooldown()
        logger.info("[AuthProfileStore] All cooldowns reset")


# Global store instance
_auth_store: AuthProfileStore | None = None


def get_auth_store() -> AuthProfileStore | None:
    """Get global auth profile store."""
    return _auth_store


def init_auth_store(config_path: str | Path | None = None) -> AuthProfileStore:
    """Initialize global auth profile store."""
    global _auth_store
    _auth_store = AuthProfileStore(config_path)
    return _auth_store