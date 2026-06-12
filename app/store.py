"""In-memory event store with filtering.

Milestone 3 replaces this with Postgres + a vector DB (same method surface) so
data survives restarts and supports semantic search. The interface stays put.
"""
from __future__ import annotations

from collections import deque
from typing import Iterable

from app.schema import Event


class EventStore:
    def __init__(self, maxlen: int = 5000):
        self._events: deque[Event] = deque(maxlen=maxlen)
        self._ids: set[str] = set()

    def add(self, event: Event) -> bool:
        """Returns False if this event id was already stored (deduped)."""
        if event.id in self._ids:
            return False
        self._ids.add(event.id)
        self._events.append(event)
        return True

    def query(
        self,
        *,
        ticker: str | None = None,
        source: str | None = None,
        min_materiality: float = 0.0,
        limit: int = 100,
    ) -> list[Event]:
        results: list[Event] = []
        for ev in reversed(self._events):  # newest first
            if ev.materiality < min_materiality:
                continue
            if source and ev.source != source:
                continue
            if ticker and ticker.upper() not in [t.upper() for t in ev.tickers]:
                continue
            results.append(ev)
            if len(results) >= limit:
                break
        return results

    def all(self) -> Iterable[Event]:
        return list(self._events)

    def __len__(self) -> int:
        return len(self._events)
