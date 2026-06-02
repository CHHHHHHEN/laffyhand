import unittest
from collections.abc import AsyncIterator

from laffyhand.agent.llm._route import Route
from laffyhand.agent.llm.specs import Protocol, Endpoint, Auth, Framing
from laffyhand.agent.llm.specs.models import LLMRequest, SystemMessage, UserMessage, Header
from laffyhand.agent.llm.specs.models import (
    StreamError,
    LLMEvent,
    StreamText,
    StreamFinish,
    Usage,
)


class _MockProtocol(Protocol):
    def build_request(self, request: LLMRequest) -> dict:  # type: ignore[override]
        return {"model": request.model, "messages": []}

    def parse_frame(self, frame: dict) -> list[LLMEvent]:  # type: ignore[override]
        return []


class _MockEndpoint(Endpoint):
    def build(self) -> str:
        return "http://mock/api/v1/chat/completions"


class _MockAuth(Auth):
    def apply(self, headers: list) -> None:
        headers.append(Header(key="Authorization", value="Bearer test"))


class _MockFraming(Framing):
    async def frames(self, response) -> AsyncIterator[dict]:  # type: ignore[override]
        raise RuntimeError("HTTP 400: test error")
        yield  # pragma: no cover


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
            model="test-model", provider="openai",
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
    async def frames(self, response) -> AsyncIterator[dict]:  # type: ignore[override]
        raise ValueError("unexpected internal error")
        yield  # pragma: no cover


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
            model="test-model", provider="openai",
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


class _MockProtocolHappy(Protocol):
    def __init__(self, events: list[LLMEvent]):
        self._events = events

    def build_request(self, request: LLMRequest) -> dict:  # type: ignore[override]
        return {"model": request.model, "messages": []}

    def parse_frame(self, frame: dict) -> list[LLMEvent]:  # type: ignore[override]
        return self._events


class _MockFramingHappy(Framing):
    def __init__(self, frames: list[dict]):
        self._frames = frames

    async def frames(self, response) -> AsyncIterator[dict]:  # type: ignore[override]
        for frame in self._frames:
            yield frame


class TestRouteHappyPath(unittest.TestCase):
    """Route.execute must yield events from protocol on successful flow."""

    def test_yields_events_from_protocol(self):
        route = Route(
            protocol=_MockProtocolHappy(
                events=[
                    StreamText(delta="hello"),
                    StreamFinish(
                        finish_reason="stop",
                        usage=Usage(input_tokens=10, output_tokens=5),
                    ),
                ]
            ),
            endpoint=_MockEndpoint(),
            auth=_MockAuth(),
            framing=_MockFramingHappy(frames=[{"dummy": True}]),
        )
        request = LLMRequest(
            model="test-model", provider="openai",
            messages=[SystemMessage(content="test")],
        )

        events = []

        async def _collect():
            async for event in route.execute(request):
                events.append(event)

        import asyncio

        asyncio.run(_collect())

        self.assertEqual(len(events), 2)
        self.assertIsInstance(events[0], StreamText)
        self.assertEqual(events[0].delta, "hello")
        self.assertIsInstance(events[1], StreamFinish)
        self.assertEqual(events[1].finish_reason, "stop")

    def test_breaks_after_stream_finish(self):
        """When StreamFinish is yielded, remaining frames from framing are skipped."""
        route = Route(
            protocol=_MockProtocolHappy(
                events=[
                    StreamFinish(
                        finish_reason="stop",
                        usage=Usage(input_tokens=5, output_tokens=3),
                    ),
                ]
            ),
            endpoint=_MockEndpoint(),
            auth=_MockAuth(),
            framing=_MockFramingHappy(
                frames=[
                    {"frame": "first"},
                    {"frame": "second"},
                ]
            ),
        )
        request = LLMRequest(
            model="test-model", provider="openai",
            messages=[UserMessage(content="hi")],
        )

        events = []

        async def _collect():
            async for event in route.execute(request):
                events.append(event)

        import asyncio

        asyncio.run(_collect())

        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], StreamFinish)

    def test_error_when_stream_ends_without_finish(self):
        """When the stream ends without a StreamFinish, a StreamError is emitted."""
        route = Route(
            protocol=_MockProtocolHappy(
                events=[
                    StreamText(delta="partial response"),
                ]
            ),
            endpoint=_MockEndpoint(),
            auth=_MockAuth(),
            framing=_MockFramingHappy(frames=[{"dummy": True}]),
        )
        request = LLMRequest(
            model="test-model", provider="openai",
            messages=[UserMessage(content="hi")],
        )

        events = []

        async def _collect():
            async for event in route.execute(request):
                events.append(event)

        import asyncio

        asyncio.run(_collect())

        self.assertEqual(len(events), 2)
        self.assertIsInstance(events[0], StreamText)
        self.assertIsInstance(events[1], StreamError)
        self.assertIn("without a finish", events[1].error)
