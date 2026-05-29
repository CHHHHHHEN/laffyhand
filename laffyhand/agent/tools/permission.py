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
        logger.trace(f"Permission check {tool_name}: {'allowed' if result else 'denied'}")
        return result

    async def ask(self, permission: str, patterns: list[str]) -> bool:
        """Interactive permission prompt. Returns True if allowed, False if denied."""
        if self._rules.get(permission) == "deny":
            logger.info(f"Permission '{permission}' denied by tool-level rule")
            return False
        for pattern in patterns:
            rule = self._rules.get(f"{permission}:{pattern}")
            if rule == "deny":
                logger.info(f"Permission '{permission}:{pattern}' denied by rule")
                return False
            if rule == "allow":
                logger.debug(f"Permission '{permission}:{pattern}' allowed by rule")
                continue
            prompt = f"\nAllow {permission} '{pattern}'? [y/N/a] "
            import asyncio
            answer = (await asyncio.to_thread(input, prompt)).strip().lower()
            if answer == "a":
                self._rules[f"{permission}:{pattern}"] = "allow"
                logger.info(f"Permission '{permission}:{pattern}' always allowed")
            elif answer == "y":
                logger.info(f"Permission '{permission}:{pattern}' allowed once")
            else:
                logger.info(f"Permission '{permission}:{pattern}' denied")
                return False
        return True
