"""A keyless mock source so the whole pipeline runs end-to-end with zero setup.

This is what lets you `uvicorn ...` and immediately see events stream, even with
no internet and no API keys. It mimics the shape of real filing/news items.
"""
from __future__ import annotations

import asyncio
import itertools
import random
from typing import AsyncIterator

from app.schema import Event
from app.sources.base import SourceAdapter

_SAMPLES = [
    ("filing", "8-K - {co} ({cik}) (Filer)", "{co} reported a material event regarding leadership changes."),
    ("filing", "10-Q - {co} ({cik}) (Filer)", "{co} filed its quarterly report; revenue rose versus the prior period."),
    ("news", "{co} beats earnings expectations", "{co} reported quarterly results above analyst estimates."),
    ("news", "{co} announces acquisition", "{co} agreed to acquire a competitor to expand its market position."),
    ("news", "{co} issues guidance cut", "{co} lowered its full-year outlook, citing softer demand."),
]
_COMPANIES = [
    ("Apple Inc.", "0000320193", "AAPL"),
    ("Microsoft Corp", "0000789019", "MSFT"),
    ("NVIDIA Corp", "0001045810", "NVDA"),
    ("Tesla Inc", "0001318605", "TSLA"),
]


class MockSource(SourceAdapter):
    name = "mock"

    def __init__(self, interval: float = 2.0):
        self.interval = interval

    async def events(self) -> AsyncIterator[Event]:
        for i in itertools.count():
            await asyncio.sleep(self.interval)
            etype, title_t, body_t = random.choice(_SAMPLES)
            co, cik, ticker = random.choice(_COMPANIES)
            yield Event(
                id=f"mock-{i}",
                source=self.name,
                type=etype,
                title=title_t.format(co=co, cik=cik),
                body=body_t.format(co=co),
                url=f"https://example.com/mock/{i}",
                tickers=[ticker],
                raw={"company": co, "cik": cik},
            )
