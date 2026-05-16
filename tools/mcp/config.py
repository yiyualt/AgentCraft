"""MCP configuration loading from file and environment variables."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.mcp.server import MCPServerConfig


@dataclass
class MCPConfig:
    """Configuration for all MCP servers."""
    servers: list[MCPServerConfig] = field(default_factory=list)
    enabled: bool = True

    @classmethod
    def load(cls, config_path: Path | str | None = None) -> MCPConfig:
        """Load configuration from file and environment.

        Priority:
        1. Explicit config_path
        2. mcp_config.json in project root (relative to this file)
        3. Environment variables (MCP_SERVER_<NAME>_COMMAND, etc.)

        Args:
            config_path: Optional explicit path to config file

        Returns:
            MCPConfig with all configured servers
        """
        config = cls()

        # Project root: 3 levels up from this file (tools/mcp/config.py)
        project_root = Path(__file__).parent.parent.parent

        # Try loading from file
        if config_path:
            file_config = cls._load_from_file(Path(config_path))
            config.servers.extend(file_config.servers)
        else:
            # Try default locations (always relative to project root)
            default_paths = [
                project_root / "mcp_config.json",
                project_root / "config" / "mcp_config.json",
            ]
            for path in default_paths:
                if path.exists():
                    file_config = cls._load_from_file(path)
                    config.servers.extend(file_config.servers)
                    break

        # Load from environment variables
        env_servers = cls._load_from_env()
        config.servers.extend(env_servers)

        # Global enable/disable
        config.enabled = os.getenv("MCP_ENABLED", "true").lower() == "true"

        return config

    @classmethod
    def _load_from_file(cls, path: Path) -> MCPConfig:
        """Load configuration from JSON file."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError) as e:
            return MCPConfig()

        servers = []
        mcp_servers = data.get("mcpServers", {})

        for name, server_data in mcp_servers.items():
            if isinstance(server_data, dict):
                server_config = MCPServerConfig(
                    name=name,
                    command=server_data.get("command", ""),
                    args=server_data.get("args", []),
                    env=server_data.get("env"),
                    cwd=server_data.get("cwd"),
                    enabled=server_data.get("enabled", True),
                )
                servers.append(server_config)

        return MCPConfig(servers=servers)

    @classmethod
    def _load_from_env(cls) -> list[MCPServerConfig]:
        """Load server configurations from environment variables.

        Format:
            MCP_SERVER_<NAME>_COMMAND=npx
            MCP_SERVER_<NAME>_ARGS=-y,@anthropic/mcp-server-filesystem,/path
            MCP_SERVER_<NAME>_ENABLED=true

        Args are comma-separated.
        """
        servers = []

        # Find all MCP_SERVER_*_COMMAND variables
        for key, value in os.environ.items():
            if key.startswith("MCP_SERVER_") and key.endswith("_COMMAND"):
                # Extract server name
                name_part = key[len("MCP_SERVER_"): -len("_COMMAND")]
                name = name_part.lower()

                # Get other config from env
                args_key = f"MCP_SERVER_{name_part}_ARGS"
                args_str = os.getenv(args_key, "")
                args = [a.strip() for a in args_str.split(",") if a.strip()]

                enabled_key = f"MCP_SERVER_{name_part}_ENABLED"
                enabled = os.getenv(enabled_key, "true").lower() == "true"

                server_config = MCPServerConfig(
                    name=name,
                    command=value,
                    args=args,
                    enabled=enabled,
                )
                servers.append(server_config)

        return servers

    def get_enabled_servers(self) -> list[MCPServerConfig]:
        """Return only enabled server configs."""
        if not self.enabled:
            return []
        return [s for s in self.servers if s.enabled and s.command]


# Default config example (for documentation)
DEFAULT_CONFIG_EXAMPLE = """
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-filesystem", "/tmp"],
      "enabled": true
    },
    "git": {
      "command": "uvx",
      "args": ["mcp-server-git"],
      "enabled": true
    }
  }
}
"""