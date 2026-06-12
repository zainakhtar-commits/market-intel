"""The engine: the producer/consumer core that makes this near-real-time.

Each source runs concurrently as a producer, pushing raw Events onto a shared
asyncio.Queue. A single consumer drains the queue, runs the pipeline, stores the
result, and broadcasts it to every connected WebSocket. This decoupling is the
key design choice: slow sources never block fast ones, and processing never
blocks ingestion.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from app.processing import process
from app.schema import Event
from app.sources.base import SourceAdapter
from app.store import EventStore

Broadcaster = Callable[[Event], Awaitable[None]]


class Engine:
    def __init__(self, sources: list[SourceAdapter], store: EventStore):
        self.sources = sources
        self.store = store
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=1000)
        self._subscribers: set[Broadcaster] = set()
        self._tasks: list[asyncio.Task] = []
        self._running = False

    # --- pub/sub for WebSocket clients -------------------------------------
    def subscribe(self, fn: Broadcaster) -> None:
        self._subscribers.add(fn)

    def unsubscribe(self, fn: Broadcaster) -> None:
        self._subscribers.discard(fn)

    async def _broadcast(self, event: Event) -> None:
        for fn in list(self._subscribers):
            try:
                await fn(event)
            except Exception:  # noqa: BLE001 - a dead client must not stop the engine
                self.unsubscribe(fn)

    # --- producer / consumer ----------------------------------------------
    async def _produce(self, source: SourceAdapter) -> None:
        async for event in source.events():
            await self.queue.put(event)

    async def _consume(self) -> None:
        while True:
            event = await self.queue.get()
            try:
                process(event)
                if self.store.add(event):  # dedupe at the store boundary
                    await self._broadcast(event)
            finally:
                self.queue.task_done()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._tasks = [asyncio.create_task(self._consume())]
        for src in self.sources:
            self._tasks.append(asyncio.create_task(self._produce(src)))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        self._running = False
