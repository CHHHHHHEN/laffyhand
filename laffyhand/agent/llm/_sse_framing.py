import json
import traceback
from typing import Iterable, Generator
from loguru import logger

from laffyhand.agent.llm.specs import Framing


class SSEFraming(Framing):
    def frames(self, response: Iterable[bytes]) -> Generator[dict, None, None]:
        for chunk in response:
            decoded = chunk.decode("utf-8").rstrip("\n")
            if not decoded:
                continue
            if decoded == "data: [DONE]":
                return
            if decoded.startswith("data: "):
                try:
                    yield json.loads(decoded[6:])
                except Exception as e:
                    logger.warning(f"Line: {decoded}\nUnexpected error: {e}\n{traceback.format_exc()}")
                    return
