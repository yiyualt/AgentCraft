"""Tests for MCP stdio client implementation.

Unit tests can run without an actual MCP server.
Integration tests require npx/uvx and actual MCP servers.
"""

from __future__ import annotations

import pytest

from tools.mcp.exceptions import MCPError, MCPServerError, MCPToolError, MCPProtocolError
from tools.mcp.protocol import (
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCNotification,
    parse_message,
)
from tools.mcp.tools import MCPTool
from tools.mcp.config import MCPConfig, MCPServerConfig
from tools.mcp.server import MCPServer


# ============================================================
# Protocol tests (no subprocess)
# ============================================================


class TestJSONRPCRequest:
    def test_to_json(self):
        req = JSONRPCRequest(id=1, method="initialize", params={"a": 1})
        json_str = req.to_json()
        assert "jsonrpc" in json_str
        assert '"id"' in json_str
        assert '"method"' in json_str

    def test_to_json_no_params(self):
        req = JSONRPCRequest(id=2, method="ping")
        json_str = req.to_json()
        assert '"params"' not in json_str


class TestJSONRPCResponse:
    def test_from_dict_success(self):
        data = {"jsonrpc": "2.0", "id": 1, "result": {"status": "ok"}}
        resp = JSONRPCResponse.from_dict(data)
        assert resp.id == 1
        assert resp.result == {"status": "ok"}
        assert resp.error is None
        assert not resp.is_error()

    def test_from_dict_error(self):
        data = {"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "fail"}}
        resp = JSONRPCResponse.from_dict(data)
        assert resp.is_error()

    def test_raise_if_error(self):
        data = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "Server error"}}
        resp = JSONRPCResponse.from_dict(data)
        with pytest.raises(MCPProtocolError) as exc_info:
            resp.raise_if_error()
        assert exc_info.value.code == -32000


class TestJSONRPCNotification:
    def test_to_json(self):
        notif = JSONRPCNotification(method="notifications/initialized")
        json_str = notif.to_json()
        assert '"id"' not in json_str
        assert '"method"' in json_str


class TestParseMessage:
    def test_parse_response(self):
        line = '{"jsonrpc":"2.0","id":1,"result":{}}'
        msg = parse_message(line)
        assert isinstance(msg, JSONRPCResponse)

    def test_parse_notification(self):
        line = '{"jsonrpc":"2.0","method":"logging/log","params":{}}'
        msg = parse_message(line)
        assert isinstance(msg, JSONRPCNotification)


# ============================================================
# Tools tests
# ============================================================


class TestMCPTool:
    def test_to_openai_tool(self):
        tool = MCPTool(
            name="filesystem.read_file",
            original_name="read_file",
            description="Read a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            server_name="filesystem",
        )
        openai_tool = tool.to_openai_tool()
        assert openai_tool["type"] == "function"
        assert openai_tool["function"]["name"] == "filesystem.read_file"
        assert openai_tool["function"]["description"] == "Read a file"

    def test_get_original_name(self):
        tool = MCPTool(
            name="git.status",
            original_name="status",
            description="",
            input_schema={},
            server_name="git",
        )
        assert tool.get_original_name() == "status"


# ============================================================
# Config tests
# ============================================================


class TestMCPConfig:
    def test_default_config(self):
        config = MCPConfig()
        assert config.servers == []
        assert config.enabled is True

    def test_load_from_env(self):
        # MCPConfig._load_from_env parses MCP_SERVER_*_COMMAND vars
        servers = MCPConfig._load_from_env()
        # Returns list (may be empty if no env vars set)
        assert isinstance(servers, list)

    def test_get_enabled_servers(self):
        config = MCPConfig(
            servers=[
                MCPServerConfig(name="a", command="npx", args=[], enabled=True),
                MCPServerConfig(name="b", command="npx", args=[], enabled=False),
            ],
            enabled=True,
        )
        enabled = config.get_enabled_servers()
        assert len(enabled) == 1
        assert enabled[0].name == "a"

    def test_disabled_globally(self):
        config = MCPConfig(
            servers=[MCPServerConfig(name="a", command="npx", args=[], enabled=True)],
            enabled=False,
        )
        assert config.get_enabled_servers() == []


class TestMCPServerConfig:
    def test_defaults(self):
        cfg = MCPServerConfig(name="test", command="npx", args=["-y", "test"])
        assert cfg.enabled is True
        assert cfg.env is None
        assert cfg.cwd is None


# ============================================================
# Exceptions tests
# ============================================================


class TestExceptions:
    def test_mcp_tool_error(self):
        err = MCPToolError(tool_name="foo", message="bar")
        assert "foo" in str(err)
        assert "bar" in str(err)
        assert err.tool_name == "foo"

    def test_mcp_protocol_error(self):
        err = MCPProtocolError(code=-32000, message="fail")
        assert err.code == -32000


# ============================================================
# Integration tests (require npx/uvx)
# ============================================================


@pytest.mark.integration
class TestMCPServerIntegration:
    """Integration tests with actual MCP servers.

    Run with: pytest tests/test_mcp.py -m integration
    """

    @pytest.mark.asyncio
    async def test_start_stop_echo_server(self):
        """Test basic lifecycle with a simple MCP server."""
        # This test requires npx to be available
        pytest.skip("Requires npx and MCP server installation")

    @pytest.mark.asyncio
    async def test_list_tools(self):
        """Test fetching tools from MCP server."""
        pytest.skip("Requires MCP server running")