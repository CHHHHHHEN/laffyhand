from __future__ import annotations

import json
from collections.abc import AsyncIterable, AsyncIterator
from loguru import logger


from laffyhand.agent.llm.specs import Framing


class SSEFraming(Framing):
    """Frames SSE (Server-Sent Events) from HTTP chunked transfer.

    Handles the case where SSE events are split across HTTP chunks by
    buffering incomplete data and only yielding complete events.
    """

    _DONE = object()

    async def frames(self, response: AsyncIterable[bytes]) -> AsyncIterator[dict]:
        buffer = ""
        async for chunk in response:
            buffer += chunk.decode("utf-8", errors="replace")
            while "\n\n" in buffer:
                raw_event, buffer = buffer.split("\n\n", 1)
                parsed = self._parse_event(raw_event)
                if parsed is self._DONE:
                    return
                if isinstance(parsed, dict):
                    yield parsed
        # Process any remaining data in the buffer (no trailing \n\n)
        if buffer.strip():
            parsed = self._parse_event(buffer)
            if isinstance(parsed, dict):
                yield parsed

    def _parse_event(self, raw: str) -> dict | None | object:
        """Parse a single SSE event string.

        Returns:
            dict: successfully parsed JSON data
            None: event was empty or not a data: line, skip it
            _DONE: [DONE] marker, stop processing
        """
        raw = raw.strip()
        if not raw:
            return None

        # Collect all data: lines within the event (there may be event:/id: lines too)
        payload_lines: list[str] = []
        is_done = False
        for line in raw.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line == "data: [DONE]" or line == "data:[DONE]":
                is_done = True
            elif line.startswith("data: "):
                payload_lines.append(line[6:])

        if is_done:
            logger.debug("SSE: [DONE] received, stopping")
            return self._DONE

        if not payload_lines:
            return None

        payload = "\n".join(payload_lines)
        try:
            return json.loads(payload)
        except json.JSONDecodeError as e:
            logger.warning(
                f"SSE JSON parse error in event ({len(raw)} chars): {e}\n"
                f"Raw (first 200): {raw[:200]}"
            )
            return None  # skip malformed frame, don't terminate the stream
