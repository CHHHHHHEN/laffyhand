from loguru import logger
from laffyhand.agent.llm.specs.models import Header
from laffyhand.agent.llm.specs import Auth


class BearerAuth(Auth):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def apply(self, headers: list[Header]) -> None:
        headers.append(Header(key="Authorization", value=f"Bearer {self.api_key}"))
        logger.debug("Bearer auth: Authorization header set")
