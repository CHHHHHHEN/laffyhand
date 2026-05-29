import json
import traceback
from collections.abc import AsyncIterable, AsyncIterator
from loguru import logger

from laffyhand.agent.llm.specs import Framing


class SSEFraming(Framing):
    async def frames(self, response: AsyncIterable[bytes]) -> AsyncIterator[dict]:
        async for chunk in response:
            decoded = chunk.decode("utf-8").rstrip("\n")
            if not decoded:
                continue
            if decoded == "data: [DONE]":
                logger.debug("SSE: [DONE] received, stopping")
                return
            if decoded.startswith("data: "):
                logger.debug(f"SSE frame: {len(decoded)} chars")
                try:
                    yield json.loads(decoded[6:])
                except json.JSONDecodeError as e:
                    logger.warning(f"Line: {decoded}\nUnexpected error: {e}\n{traceback.format_exc()}")
                    return
