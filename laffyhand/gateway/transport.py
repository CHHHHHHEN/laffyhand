from __future__ import annotations

import sys
import asyncio
from abc import ABC, abstractmethod
from asyncio import Queue, StreamReader


class Transport(ABC):
    connection_id: str = ""

    @abstractmethod
    async def send(self, data: str) -> None: ...

    @abstractmethod
    async def recv(self) -> str: ...

    @abstractmethod
    async def close(self) -> None: ...


class StdioTransport(Transport):
    def __init__(self, reader: StreamReader | None = None) -> None:
        self.connection_id = "stdio"
        self._reader: StreamReader | None = reader
        self._writer = sys.stdout
        self._closed = False

    async def send(self, data: str) -> None:
        if self._closed:
            return
        self._writer.write(data + "\n")
        self._writer.flush()

    async def recv(self) -> str:
        if self._reader is None:
            loop = asyncio.get_running_loop()
            reader = StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)
            await loop.connect_read_pipe(lambda: protocol, sys.stdin)
            self._reader = reader
        line = await self._reader.readline()
        return line.decode().rstrip("\n")

    async def close(self) -> None:
        self._closed = True


class InProcessTransport(Transport):
    connection_id: str = "inprocess"

    def __init__(self, recv_queue: Queue[str], send_queue: Queue[str]) -> None:
        self._recv_queue = recv_queue
        self._send_queue = send_queue
        self._closed = False

    async def send(self, data: str) -> None:
        if self._closed:
            return
        await self._send_queue.put(data)

    async def recv(self) -> str:
        if self._closed:
            return ""
        return await self._recv_queue.get()

    async def close(self) -> None:
        self._closed = True

    @staticmethod
    def create_pair() -> tuple[InProcessTransport, InProcessTransport]:
        a_to_b: Queue[str] = Queue()
        b_to_a: Queue[str] = Queue()
        a = InProcessTransport(recv_queue=b_to_a, send_queue=a_to_b)
        b = InProcessTransport(recv_queue=a_to_b, send_queue=b_to_a)
        return a, b


class _NullTransport(Transport):
    connection_id: str = "null"

    async def send(self, data: str) -> None:
        pass

    async def recv(self) -> str:
        return ""

    async def close(self) -> None:
        pass
