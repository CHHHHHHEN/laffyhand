import http.client as client
import json
from urllib.parse import urlparse
from typing import Generator, Optional
from loguru import logger

from laffyhand.agent.schemas import LLMRequest, StreamEvent, StreamFinish
from laffyhand.agent.llm.specs import Protocol, Endpoint, Auth, Framing


class HTTPClient:
    def __init__(self, timeout: int = 30, max_retries: int = 0) -> None:
        self.timeout = timeout
        self.max_retries = max_retries

    def stream(self, method: str, url: str, headers: dict, body: bytes) -> Generator[bytes, None, None]:
        parsed = urlparse(url)
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        ConnectionClass = client.HTTPSConnection if parsed.scheme == "https" else client.HTTPConnection
        conn = ConnectionClass(host=parsed.netloc, timeout=self.timeout)
        try:
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            if response.status != 200:
                error_body = response.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"HTTP {response.status}: {error_body}")
            yield from response
        finally:
            conn.close()


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

    def execute(self, request: LLMRequest) -> Generator[StreamEvent, None, None]:
        url = self.endpoint.build(request.model)
        body_dict = self.protocol.build_request(request)
        body = json.dumps(body_dict).encode("utf-8")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        self.auth.apply(headers)

        logger.debug(f"Route POST {url}")

        response = self.http_client.stream("POST", url, headers, body)
        for frame in self.framing.frames(response):
            events = self.protocol.parse_frame(frame)
            for event in events:
                yield event
            if any(isinstance(e, StreamFinish) for e in events):
                break
