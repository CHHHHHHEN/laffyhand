from __future__ import annotations


class LaffyHandError(Exception):
    """Base exception for all LaffyHand errors."""


class ConfigError(LaffyHandError):
    """Configuration-related errors."""


class SessionError(LaffyHandError):
    """Session operation errors."""


class ToolExecutionError(LaffyHandError):
    """Tool execution errors."""


class MCPError(LaffyHandError):
    """MCP server connection or execution errors."""
