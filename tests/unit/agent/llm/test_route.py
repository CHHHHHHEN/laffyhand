import unittest
from collections.abc import AsyncIterator

from laffyhand.agent.llm._route import Route
from laffyhand.agent.llm.specs import Protocol, Endpoint, Auth, Framing
from laffyhand.agent.schemas import (
    LLMRequest, SystemMessage, UserMessage, StreamError, StreamEvent,
)


class _MockProtocol(Protocol):
    def build_request(self, request: LLMRequest) -> dict:
        return {"model": request.model, "messages": []}

    def parse_frame(self, frame: dict) -> list[StreamEvent]:
        return []


class _MockEndpoint(Endpoint):
    def build(self, model: str) -> str:
        return "http://mock/api/v1/chat/completions"


class _MockAuth(Auth):
    def apply(self, headers: dict) -> None:
        headers["Authorization"] = "Bearer test"


class _MockFraming(Framing):
    async def frames(self, response) -> AsyncIterator[dict]:
        # Simulate a RuntimeError during streaming (e.g. HTTP 400 from API)
        raise RuntimeError("HTTP 400: test error")
        yield {}  # never reached


class TestRouteErrorHandling(unittest.TestCase):
    """Route.execute must catch RuntimeError and yield StreamError."""

    def test_runtime_error_yields_stream_error(self):
        route = Route(
            protocol=_MockProtocol(),
            endpoint=_MockEndpoint(),
            auth=_MockAuth(),
            framing=_MockFraming(),
        )
        request = LLMRequest(
            model="test-model",
            messages=[SystemMessage(content="test"), UserMessage(content="hello")],
        )

        events = []
        async def _collect():
            async for event in route.execute(request):
                events.append(event)

        import asyncio
        asyncio.run(_collect())

        self.assertEqual(len(events), 1, "Expected exactly one StreamError event")
        self.assertIsInstance(events[0], StreamError)
        self.assertIn("HTTP 400", events[0].error)


class _FramingUnexpectedError(Framing):
    async def frames(self, response) -> AsyncIterator[dict]:
        raise ValueError("unexpected internal error")
        yield {}  # never reached


class TestRouteUnexpectedError(unittest.TestCase):
    """Route.execute must catch any Exception and yield StreamError."""

    def test_unexpected_error_yields_stream_error(self):
        route = Route(
            protocol=_MockProtocol(),
            endpoint=_MockEndpoint(),
            auth=_MockAuth(),
            framing=_FramingUnexpectedError(),
        )
        request = LLMRequest(
            model="test-model",
            messages=[SystemMessage(content="test")],
        )

        events = []
        async def _collect():
            async for event in route.execute(request):
                events.append(event)

        import asyncio
        asyncio.run(_collect())

        self.assertEqual(len(events), 1, "Expected exactly one StreamError event")
        self.assertIsInstance(events[0], StreamError)
