from __future__ import annotations

import asyncio
import contextvars
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from loguru import logger

if TYPE_CHECKING:
    from laffyhand.core.tools.registry import ToolRegistry


Rule = Literal["allow", "deny"]

request_callback: contextvars.ContextVar[
    Callable[[str, str], Awaitable[tuple[bool, str | None]]] | None
] = contextvars.ContextVar("request_callback", default=None)


class PermissionManager:
    def __init__(self, parent: PermissionManager | None = None) -> None:
        self._rules: dict[str, Rule] = {}
        self._parent = parent
        self.request_callback: (
            Callable[[str, str], Awaitable[tuple[bool, str | None]]] | None
        ) = None

    def deny(self, tool_name: str) -> None:
        self._rules[tool_name] = "deny"

    def _get_rule(self, key: str) -> str | None:
        """Check self's rules first, then delegate to parent if not found."""
        val = self._rules.get(key)
        if val is not None:
            return val
        if self._parent is not None:
            return self._parent._get_rule(key)
        return None

    def get_rules(self) -> dict[str, Rule]:
        merged = dict(self._rules)
        if self._parent is not None:
            parent_rules = self._parent.get_rules()
            parent_rules.update(merged)
            return parent_rules
        return merged

    def add_rule(self, key: str, rule: Rule) -> None:
        self._rules[key] = rule

    def check(self, tool_name: str) -> bool:
        result = self._get_rule(tool_name)
        allowed = result != "deny" if result is not None else True
        logger.trace(
            f"Permission check {tool_name}: {'allowed' if allowed else 'denied'}"
        )
        return allowed

    async def ask(
        self, permission: str, patterns: list[str]
    ) -> tuple[bool, str | None]:
        """Interactive permission prompt. Returns (allowed, reason) where reason is populated on denial."""
        blanket = self._get_rule(permission)
        if blanket == "deny":
            logger.info(f"Permission '{permission}' denied by tool-level rule")
            return (False, None)
        if blanket == "allow":
            logger.info(f"Permission '{permission}' allowed by tool-level rule")
            return (True, None)
        for pattern in patterns:
            rule = self._get_rule(f"{permission}:{pattern}")
            if rule == "deny":
                logger.info(f"Permission '{permission}:{pattern}' denied by rule")
                return (False, None)
            if rule == "allow":
                continue
            callback = request_callback.get() or self.request_callback
            if callback is not None:
                allowed, reason = await callback(permission, pattern)
                if allowed:
                    logger.info(
                        f"Permission '{permission}:{pattern}' allowed via callback"
                    )
                else:
                    logger.info(
                        f"Permission '{permission}:{pattern}' denied via callback"
                    )
                    return (False, reason)
                continue
            prompt = f"\nAllow {permission} '{pattern}'? [y/N/a] "
            try:
                answer = (await asyncio.to_thread(input, prompt)).strip().lower()
            except EOFError, OSError:
                raise RuntimeError(
                    f"Cannot prompt for permission '{permission}:{pattern}' — "
                    "no interactive terminal available. "
                    "Use PermissionManager.allow/deny to configure rules in non-interactive mode."
                )
            if answer == "a":
                self._rules[f"{permission}:{pattern}"] = "allow"
                logger.info(f"Permission '{permission}:{pattern}' always allowed")
            elif answer == "y":
                logger.info(f"Permission '{permission}:{pattern}' allowed once")
            else:
                logger.info(f"Permission '{permission}:{pattern}' denied")
                return (False, None)
        return (True, None)

    def _check_parent_rules(self, permission: str, path: str) -> str | None:
        """Walk up *path* (including itself) and return the nearest ancestor
        that has an explicit rule in *self._rules* (``"allow"`` or ``"deny"``).

        Checks the path itself first, then each parent directory up to root.
        Delegates to parent if no rule found in self.
        Returns ``None`` when no ancestor has a rule.
        """
        needle = f"{permission}:"
        p = Path(path)
        for candidate in (p, *p.parents):
            rule = self._get_rule(f"{needle}{candidate}")
            if rule is not None:
                return rule
        return None

    async def require_path(
        self, tool_name: str, path: str | Path, workspace: str | Path | None
    ) -> tuple[bool, str | None]:
        """Check if a path is within the workspace. Returns (ok, reason)."""
        from laffyhand.core.tools.file._path_boundary import is_within

        if workspace is None:
            return (True, None)
        resolved = str(Path(path).resolve())
        if is_within(resolved, workspace):
            return (True, None)
        logger.info(f"Path {resolved} is outside workspace {workspace}")

        # All file-tool outside-workspace checks share a single permission name
        # so that an "always allow" for one tool (e.g. read) also covers others
        permission = "outside_workspace"
        parent_rule = self._check_parent_rules(permission, resolved)
        if parent_rule == "allow":
            logger.info(f"Path {resolved} allowed by parent-rule {permission}")
            return (True, None)
        if parent_rule == "deny":
            logger.info(f"Path {resolved} denied by parent-rule {permission}")
            return (False, None)

        result = await self.ask(permission, [resolved])

        # When the user chose "always allow" (rule stored for exact path),
        # also add a rule for the parent directory so that sibling files
        # and subdirectories are automatically covered.
        rule_key = f"{permission}:{resolved}"
        if result[0] and self._get_rule(rule_key) == "allow":
            parent = str(Path(resolved).parent)
            if parent != resolved:
                parent_key = f"{permission}:{parent}"
                if self._get_rule(parent_key) is None:
                    self._rules[parent_key] = "allow"
                    logger.info(
                        f"Parent directory {parent_key} auto-allowed by rule propagation"
                    )

        return result


_SUBAGENT_EXCLUDED_TOOLS: frozenset[str] = frozenset({"task"})


class SubagentPermissions:
    @staticmethod
    def compose(
        parent_permission: PermissionManager,
        agent_permission: dict[str, Any],
        parent_session_permission: PermissionManager | None = None,
    ) -> PermissionManager:
        child = PermissionManager(parent=parent_permission)
        agent_deny = set(agent_permission.get("deny", []))
        for name in agent_deny:
            child.deny(name)
        if parent_session_permission is not None:
            for name, rule in parent_session_permission.get_rules().items():
                if rule == "deny":
                    child.deny(name)
        return child

    @staticmethod
    def filter_registry(
        registry: ToolRegistry,
        permission: PermissionManager,
    ) -> ToolRegistry:
        from laffyhand.core.tools.registry import ToolRegistry as _ToolRegistry

        filtered = _ToolRegistry(permission=permission)
        for name, tool in registry.list_tools().items():
            if name in _SUBAGENT_EXCLUDED_TOOLS:
                continue
            if permission.check(name):
                # Sub-agent tools should not have timeout limits —
                # exploration tasks like large codebase searches can exceed 120s
                tool.timeout = 0
                filtered.register_tool(tool)
        filtered.result_post_processor = registry.result_post_processor
        filtered.workspace = registry.workspace
        return filtered
