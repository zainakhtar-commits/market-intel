"""Source adapter contract.

Every source is an async generator of Events. The engine just `async for`s over
each adapter concurrently, so adding a new source (news API, market data, Reddit)
means writing one class — nothing downstream changes.
"""
from __future__ import annotations

import abc
from typing import AsyncIterator

from app.schema import Event


class SourceAdapter(abc.ABC):
    """Base class for all ingestion sources."""

    #: short, stable identifier used in Event.source
    name: str = "base"

    @abc.abstractmethod
    async def events(self) -> AsyncIterator[Event]:
        """Yield normalized Events as they arrive.

        Implementations should yield partially-filled Events (title/body/url/
        tickers if cheaply known); the pipeline fills sentiment/materiality/
        summary. Should run indefinitely for near-real-time sources.
        """
        raise NotImplementedError
        # pragma: no cover
        yield  # makes this an async generator for type-checkers
