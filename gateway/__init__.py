"""Gateway module - Protocol version management."""

from .version import (
    GATEWAY_VERSION,
    VERSION_HISTORY,
    VersionCompatibility,
    VersionInfo,
    check_version_compatibility,
    get_version_headers,
    validate_client_version,
    negotiate_version,
    get_changelog,
    get_migration_guide,
)

__all__ = [
    "GATEWAY_VERSION",
    "VERSION_HISTORY",
    "VersionCompatibility",
    "VersionInfo",
    "check_version_compatibility",
    "get_version_headers",
    "validate_client_version",
    "negotiate_version",
    "get_changelog",
    "get_migration_guide",
]