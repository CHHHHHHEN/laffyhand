import json
import unittest
from collections.abc import AsyncIterator

from laffyhand.llm._sse_framing import SSEFraming
from laffyhand.llm.specs.models import Frame


class _AsyncIter:
    """Helper to create an async iterable from a list of byte chunks."""

    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    def __aiter__(self) -> AsyncIterator[bytes]:
        return _AsyncIterIterator(self._chunks)


class _AsyncIterIterator:
    def __init__(self, chunks: list[bytes]):
        self._chunks = list(chunks)

    async def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class TestSSEFraming(unittest.TestCase):
    """SSEFraming must buffer incomplete chunks and handle malformed frames."""

    def _collect(self, chunks: list[bytes]) -> list[Frame]:
        framing = SSEFraming()
        result = []

        async def _run():
            async for frame in framing.frames(_AsyncIter(chunks)):
                result.append(frame)

        import asyncio

        asyncio.run(_run())
        return result

    def test_complete_single_frame(self):
        data = json.dumps({"id": "1", "choices": [{"delta": {"content": "hello"}}]})
        frames = self._collect([f"data: {data}\n\n".encode()])
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].data["id"], "1")

    def test_multiple_frames(self):
        data1 = json.dumps({"id": "1", "choices": [{"delta": {"content": "hello"}}]})
        data2 = json.dumps({"id": "2", "choices": [{"delta": {"content": " world"}}]})
        frames = self._collect(
            [
                f"data: {data1}\n\ndata: {data2}\n\n".encode(),
            ]
        )
        self.assertEqual(len(frames), 2)

    def test_chunk_split_in_middle_of_json(self):
        """SSE frame split across chunks: JSON truncated across chunk boundary."""
        json_str = json.dumps(
            {
                "id": "split-id-12345",
                "choices": [{"delta": {"content": "hello"}}],
            }
        )
        part1 = f"data: {json_str[:25]}".encode()
        part2 = f"{json_str[25:]}\n\n".encode()
        frames = self._collect([part1, part2])
        self.assertEqual(len(frames), 1, "Should reassemble split JSON")
        self.assertEqual(frames[0].data["id"], "split-id-12345")

    def test_chunk_split_between_events(self):
        """Two SSE frames where the boundary falls inside a chunk."""
        data1 = json.dumps({"id": "first"})
        data2 = json.dumps({"id": "second"})
        # First event complete, second event starts in same chunk
        chunk = f"data: {data1}\n\ndata: {data2[:10]}".encode()
        rest = f"{data2[10:]}\n\n".encode()
        frames = self._collect([chunk, rest])
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].data["id"], "first")
        self.assertEqual(frames[1].data["id"], "second")

    def test_malformed_json_does_not_stop_stream(self):
        """A malformed JSON frame should be skipped, not terminate the stream."""
        valid_data = json.dumps(
            {"id": "valid", "choices": [{"delta": {"content": "ok"}}]}
        )
        frames = self._collect(
            [
                f"data: {valid_data}\n\n".encode(),
                b"data: {truncated json\n\n",
                f"data: {valid_data}\n\n".encode(),
            ]
        )
        self.assertEqual(len(frames), 2, "Should skip malformed frame, keep valid ones")
        self.assertEqual(frames[0].data["id"], "valid")
        self.assertEqual(frames[1].data["id"], "valid")

    def test_done_marker(self):
        """[DONE] marker should terminate the stream."""
        data = json.dumps({"id": "1", "choices": [{"delta": {"content": "hello"}}]})
        frames = self._collect(
            [
                f"data: {data}\n\n".encode(),
                b"data: [DONE]\n\n",
                f"data: {json.dumps({'id': 'after'})}\n\n".encode(),
            ]
        )
        self.assertEqual(len(frames), 1, "Should stop at [DONE] marker")

    def test_multiple_data_lines_same_chunk(self):
        """Multiple complete SSE events in a single chunk."""
        d1 = json.dumps({"id": "a", "choices": [{"delta": {"content": "a"}}]})
        d2 = json.dumps({"id": "b", "choices": [{"delta": {"content": "b"}}]})
        d3 = json.dumps({"id": "c", "choices": [{"delta": {"content": "c"}}]})
        frames = self._collect(
            [
                f"data: {d1}\n\ndata: {d2}\n\ndata: {d3}\n\n".encode(),
            ]
        )
        self.assertEqual(len(frames), 3)

    def test_non_data_lines_skipped(self):
        """Lines like 'event: ...' or 'id: ...' should be silently skipped."""
        data = json.dumps({"choices": [{"delta": {"content": "only"}}]})
        frames = self._collect(
            [
                b"event: message\n",
                b"id: 42\n",
                f"data: {data}\n\n".encode(),
            ]
        )
        self.assertEqual(len(frames), 1)

    def test_empty_frames_skipped(self):
        """Empty data lines should be skipped."""
        data = json.dumps({"choices": [{"delta": {"content": "after empty"}}]})
        frames = self._collect(
            [
                b"\n\n",
                b"data: \n\n",
                f"data: {data}\n\n".encode(),
            ]
        )
        self.assertEqual(len(frames), 1)

    def test_leftover_data_without_trailing_newline(self):
        """Data remaining in buffer after stream ends should still be processed."""
        data = json.dumps({"id": "no-trailing-nl"})
        frames = self._collect(
            [
                f"data: {data}".encode(),  # no \n\n at the end
            ]
        )
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].data["id"], "no-trailing-nl")

    def test_multi_data_lines_same_event(self):
        """Multiple data: lines within one SSE event are joined with newline and parsed as combined JSON."""
        frames = self._collect(
            [
                b'data: {"valid": true}\ndata: \n\n',
            ]
        )
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].data, {"valid": True})

    def test_done_marker_no_space(self):
        """[DONE] without space after colon should also terminate."""
        data = json.dumps({"id": "before-done"})
        frames = self._collect(
            [
                f"data: {data}\n\n".encode(),
                b"data:[DONE]\n\n",
            ]
        )
        self.assertEqual(len(frames), 1)

    def test_utf8_decode_error_replaced(self):
        """Invalid UTF-8 bytes should be replaced without crashing."""
        frames = self._collect(
            [
                b'data: {"valid": true}\n\n',
                b'data: {"bad": \xff\xfe}\n\n',
                b'data: {"after": true}\n\n',
            ]
        )
        self.assertEqual(
            len(frames), 2, "Skip malformed frame with replacement chars, keep others"
        )
