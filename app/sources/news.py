"""Real news source — Google News RSS (free, no API key).

For each tracked ticker we poll Google News' RSS search, dedupe headlines, and
emit Events tagged with that ticker. Because we query per ticker, entity
resolution is exact — we already know which company each headline is about.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator
from xml.etree import ElementTree as ET

import httpx

from app.schema import Event
from app.sources.base import SourceAdapter

USER_AGENT = "MarketIntel/0.4 (contact: akhtarzahir@gmail.com)"
# when:7d keeps it to the last week so we don't replay ancient news on startup
RSS_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


class GoogleNewsSource(SourceAdapter):
    name = "news"

    def __init__(self, tickers: list[str], poll_interval: float = 90.0):
        self.tickers = [t.strip().upper() for t in tickers if t.strip()]
        self.poll_interval = poll_interval
        self._seen: set[str] = set()
        self._client: httpx.AsyncClient | None = None

    async def _client_get(self, url: str) -> str | None:
        if self._client is None:
            self._client = httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=20.0)
        try:
            r = await self._client.get(url)
            r.raise_for_status()
            return r.text
        except Exception as exc:  # noqa: BLE001 - one bad poll must not kill the source
            print(f"[news] fetch failed: {exc}")
            return None

    def _parse(self, xml_text: str, ticker: str) -> list[Event]:
        out: list[Event] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            print(f"[news] parse error: {exc}")
            return out
        channel = root.find("channel")
        if channel is None:
            return out
        for item in channel.findall("item"):
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or link).strip()
            key = f"{ticker}:{guid}"
            if not guid or key in self._seen:
                continue
            self._seen.add(key)

            raw_title = (item.findtext("title") or "").strip()
            # Google News titles are "Headline - Publisher"; split the publisher out.
            title, _, publisher = raw_title.rpartition(" - ")
            title = title or raw_title
            pub = (item.findtext("pubDate") or "").strip()

            out.append(Event(
                id=guid,
                source=self.name,
                type="news",
                title=title,
                body=f"{title} ({publisher})" if publisher else title,
                url=link,
                tickers=[ticker],
                entities=[ticker],
                raw={"publisher": publisher, "pubDate": pub, "query_ticker": ticker},
            ))
        return out

    async def events(self) -> AsyncIterator[Event]:
        while True:
            for ticker in self.tickers:
                xml = await self._client_get(RSS_URL.format(query=f"{ticker}+stock"))
                if xml:
                    for ev in self._parse(xml, ticker):
                        yield ev
                await asyncio.sleep(1.0)  # be polite between ticker queries
            await asyncio.sleep(self.poll_interval)
