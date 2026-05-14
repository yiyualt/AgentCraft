"""Gateway version management and protocol negotiation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# Gateway version history
GATEWAY_VERSION = "1.0.0"

VERSION_HISTORY = {
    "1.0.0": {
        "date": "2025-05-15",
        "changes": [
            "Initial stable release",
            "Multi-provider support",
            "Vector memory integration",
            "ACP control plane",
            "Automation & scheduling",
            "Webhook triggers",
        ],
    },
    "0.9.0": {
        "date": "2025-05-10",
        "changes": [
            "Added fork mechanism",
            "Auto-compaction",
            "Canvas workspace",
        ],
    },
    "0.8.0": {
        "date": "2025-05-01",
        "changes": [
            "Sandbox execution",
            "MCP tool integration",
            "Channel routing",
        ],
    },
}


class VersionCompatibility(Enum):
    """Version compatibility status."""
    COMPATIBLE = "compatible"          # Full compatibility
    DEPRECATED = "deprecated"          # Client version older but works
    INCOMPATIBLE = "incompatible"      # Major version mismatch
    FUTURE = "future"                  # Client version newer


@dataclass
class VersionInfo:
    """Version information."""
    version: str
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, version_str: str) -> VersionInfo:
        """Parse version string like '1.0.0'."""
        parts = version_str.split(".")
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return cls(version_str, major, minor, patch)


def check_version_compatibility(
    client_version: str,
    gateway_version: str = GATEWAY_VERSION,
) -> VersionCompatibility:
    """Check compatibility between client and gateway versions.

    Rules:
    - Major must match exactly
    - Minor: client can be lower (deprecated) or same (compatible)
    - Patch: any difference is ok

    Returns:
        VersionCompatibility status
    """
    client = VersionInfo.parse(client_version)
    gateway = VersionInfo.parse(gateway_version)

    # Major mismatch = incompatible
    if client.major != gateway.major:
        if client.major > gateway.major:
            return VersionCompatibility.FUTURE
        return VersionCompatibility.INCOMPATIBLE

    # Same major, check minor
    if client.minor == gateway.minor:
        return VersionCompatibility.COMPATIBLE
    elif client.minor < gateway.minor:
        return VersionCompatibility.DEPRECATED
    else:
        return VersionCompatibility.FUTURE


def get_version_headers() -> dict[str, str]:
    """Get standard version headers for responses."""
    return {
        "X-Gateway-Version": GATEWAY_VERSION,
        "X-Gateway-Version-Date": VERSION_HISTORY[GATEWAY_VERSION]["date"],
    }


def validate_client_version(client_version: str | None) -> tuple[bool, str]:
    """Validate client version header.

    Returns:
        (is_valid, message)
    """
    if not client_version:
        # No version header - allow but log warning
        logger.warning("[Gateway] Client sent no version header")
        return True, "No version provided"

    compatibility = check_version_compatibility(client_version)

    if compatibility == VersionCompatibility.COMPATIBLE:
        return True, f"Compatible: client {client_version}"
    elif compatibility == VersionCompatibility.DEPRECATED:
        logger.warning(
            f"[Gateway] Client version {client_version} is deprecated, "
            f"current is {GATEWAY_VERSION}"
        )
        return True, f"Deprecated: client {client_version}, please upgrade to {GATEWAY_VERSION}"
    elif compatibility == VersionCompatibility.INCOMPATIBLE:
        return False, f"Incompatible: client {client_version}, gateway requires major version {GATEWAY_VERSION.split('.')[0]}"
    elif compatibility == VersionCompatibility.FUTURE:
        logger.info(
            f"[Gateway] Client version {client_version} is newer than gateway {GATEWAY_VERSION}"
        )
        return True, f"Future: client {client_version} newer than gateway"

    return True, "Unknown status"


def negotiate_version(
    client_versions: list[str],
    gateway_version: str = GATEWAY_VERSION,
) -> str:
    """Negotiate best compatible version.

    If client supports multiple versions, pick best compatible one.
    If none compatible, return gateway version.

    Args:
        client_versions: List of versions client supports
        gateway_version: Current gateway version

    Returns:
        Selected version to use
    """
    gateway = VersionInfo.parse(gateway_version)

    # Try each client version in order
    for client_version in client_versions:
        client = VersionInfo.parse(client_version)

        # Exact match
        if client.version == gateway_version:
            return gateway_version

        # Same major and compatible minor
        if client.major == gateway.major and client.minor <= gateway.minor:
            return gateway_version

    # No compatible version found - use gateway version
    return gateway_version


def get_changelog(version: str | None = None) -> dict[str, Any]:
    """Get changelog for a specific version or all versions."""
    if version:
        return VERSION_HISTORY.get(version, {})

    # Return all changelog
    return {
        "current": GATEWAY_VERSION,
        "history": VERSION_HISTORY,
    }


def get_migration_guide(from_version: str, to_version: str) -> dict[str, Any]:
    """Get migration guide between versions.

    Identifies breaking changes and provides guidance.
    """
    from_info = VersionInfo.parse(from_version)
    to_info = VersionInfo.parse(to_version)

    guide = {
        "from": from_version,
        "to": to_version,
        "breaking_changes": [],
        "deprecations": [],
        "new_features": [],
    }

    # Collect changes between versions
    versions_to_check = []
    for v in sorted(VERSION_HISTORY.keys()):
        v_info = VersionInfo.parse(v)
        if v_info.major >= from_info.major and v_info.minor >= from_info.minor:
            if v_info.major <= to_info.major and v_info.minor <= to_info.minor:
                versions_to_check.append(v)

    for v in versions_to_check:
        changes = VERSION_HISTORY.get(v, {}).get("changes", [])
        # Heuristic: if version major increased, changes are breaking
        v_info = VersionInfo.parse(v)
        if v_info.major > from_info.major:
            guide["breaking_changes"].extend(changes)
        elif v_info.minor > from_info.minor:
            guide["new_features"].extend(changes)

    return guide