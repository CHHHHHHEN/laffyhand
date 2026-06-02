import json
from urllib.parse import urlparse
from collections.abc import AsyncIterator
from typing import Optional
from pydantic import BaseModel
from loguru import logger
import httpx


def _redact_url(url: str) -> str:
    parsed = urlparse(url)
    redacted = parsed._replace(
        netloc=parsed.hostname if parsed.hostname else parsed.netloc,
        query="",
        fragment="",
    )
    return redacted.geturl()


from laffyhand.agent.llm.specs.models import LLMRequest, Header
from laffyhand.agent.schemas import LLMEvent, StreamFinish, StreamError
from laffyhand.agent.llm.specs import Protocol, Endpoint, Auth, Framing


class HTTPClient:
    def __init__(self, timeout: int = 30, max_retries: int = 0) -> None:
        self.timeout = timeout
        self.max_retries = max_retries

    async def stream(
        self, method: str, url: str, headers: dict[str, str], body: bytes
    ) -> AsyncIterator[bytes]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as client:
            async with client.stream(
                method, url, headers=headers, content=body
            ) as response:
                logger.debug(f"HTTP {response.status_code} from {_redact_url(url)}")
                if response.status_code != 200:
                    error_body = await response.aread()
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}: {error_body.decode()}",
                        request=response.request,
                        response=response,
                    )
                async for chunk in response.aiter_bytes():
                    yield chunk


class Route:
    def __init__(
        self,
        protocol: Protocol,
        endpoint: Endpoint,
        auth: Auth,
        framing: Framing,
        http_client: Optional[HTTPClient] = None,
    ) -> None:
        self.protocol = protocol
        self.endpoint = endpoint
        self.auth = auth
        self.framing = framing
        self.http_client = http_client or HTTPClient()

    async def execute(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        url = self.endpoint.build()
        body_dict = self.protocol.build_request(request)
        if isinstance(body_dict, BaseModel):
            body = json.dumps(body_dict.model_dump()).encode("utf-8")
        else:
            body = json.dumps(body_dict).encode("utf-8")
        headers: list[Header] = [Header(key="Content-Type", value="application/json")]
        self.auth.apply(headers)

        logger.debug(f"Route POST {_redact_url(url)}")

        response = self.http_client.stream(
            "POST", url, {h.key: h.value for h in headers}, body
        )
        finished = False
        try:
            async for frame in self.framing.frames(response):
                events = self.protocol.parse_frame(frame)
                for event in events:
                    if isinstance(event, StreamFinish):
                        finished = True
                    yield event
                if any(isinstance(e, StreamFinish) for e in events):
                    break
        except httpx.HTTPStatusError as e:
            logger.error(f"LLM request failed with HTTP {e.response.status_code}: {e}")
            yield StreamError(error=str(e))
            finished = True
        except httpx.RequestError as e:
            logger.error(f"LLM request connection error: {e}")
            yield StreamError(error=str(e))
            finished = True
        except Exception as e:
            logger.exception("Unexpected error in LLM stream")
            yield StreamError(error=str(e))
            finished = True

        if not finished:
            logger.error(
                "LLM stream ended without a finish event — the response may be truncated"
            )
            yield StreamError(error="LLM stream ended without a finish event")
