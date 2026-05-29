from typing import Literal

from loguru import logger


Rule = Literal["allow", "deny"]


class PermissionManager:
    def __init__(self) -> None:
        self._rules: dict[str, Rule] = {}

    def allow(self, tool_name: str) -> None:
        self._rules[tool_name] = "allow"

    def deny(self, tool_name: str) -> None:
        self._rules[tool_name] = "deny"

    def check(self, tool_name: str) -> bool:
        result = self._rules.get(tool_name, "allow") == "allow"
        logger.debug(f"Permission check {tool_name}: {'allowed' if result else 'denied'}")
        return result
