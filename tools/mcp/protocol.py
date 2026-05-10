"""MCP JSON-RPC protocol message handling.

MCP uses JSON-RPC 2.0 format for all messages.
Messages are newline-delimited and must not contain embedded newlines.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from tools.mcp.exceptions import MCPProtocolError


@dataclass
class JSONRPCRequest:
    """JSON-RPC 2.0 request message."""
    id: int | str
    method: str
    jsonrpc: str = "2.0"
    params: dict[str, Any] | None = None

    def to_json(self) -> str:
        data = {
            "jsonrpc": self.jsonrpc,
            "id": self.id,
            "method": self.method,
        }
        if self.params is not None:
            data["params"] = self.params
        return json.dumps(data, ensure_ascii=False)


@dataclass
class JSONRPCResponse:
    """JSON-RPC 2.0 response message."""
    id: int | str
    jsonrpc: str = "2.0"
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JSONRPCResponse:
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id"),
            result=data.get("result"),
            error=data.get("error"),
        )

    def is_error(self) -> bool:
        return self.error is not None

    def raise_if_error(self) -> None:
        if self.error:
            code = self.error.get("code")
            message = self.error.get("message", "Unknown error")
            raise MCPProtocolError(code=code, message=message)


@dataclass
class JSONRPCNotification:
    """JSON-RPC 2.0 notification (no id, no response expected)."""
    method: str
    jsonrpc: str = "2.0"
    params: dict[str, Any] | None = None

    def to_json(self) -> str:
        data = {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
        }
        if self.params is not None:
            data["params"] = self.params
        return json.dumps(data, ensure_ascii=False)


@dataclass
class MCPInitializeParams:
    """Parameters for initialize request."""
    client_info: dict[str, str] = field(default_factory=lambda: {"name": "gateway", "version": "0.1.0"})
    protocol_version: str = "2024-11-05"
    capabilities: dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPInitializeResult:
    """Result from initialize request."""
    protocol_version: str
    server_info: dict[str, str]
    capabilities: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPInitializeResult:
        return cls(
            protocol_version=data.get("protocolVersion", ""),
            server_info=data.get("serverInfo", {}),
            capabilities=data.get("capabilities", {}),
        )


def parse_message(line: str) -> JSONRPCResponse | JSONRPCNotification:
    """Parse a JSON-RPC message from a line."""
    data = json.loads(line)
    if "id" in data:
        return JSONRPCResponse.from_dict(data)
    else:
        return JSONRPCNotification(
            jsonrpc=data.get("jsonrpc", "2.0"),
            method=data.get("method", ""),
            params=data.get("params"),
        )