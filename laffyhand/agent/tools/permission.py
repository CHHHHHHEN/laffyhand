from typing import Literal


Rule = Literal["allow", "deny"]


class PermissionManager:
    def __init__(self) -> None:
        self._rules: dict[str, Rule] = {}

    def allow(self, tool_name: str) -> None:
        self._rules[tool_name] = "allow"

    def deny(self, tool_name: str) -> None:
        self._rules[tool_name] = "deny"

    def check(self, tool_name: str) -> bool:
        return self._rules.get(tool_name, "allow") == "allow"
