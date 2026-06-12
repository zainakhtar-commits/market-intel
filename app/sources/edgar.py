"""SEC EDGAR adapter — the first REAL source (Milestone 2).

Free, public, no API key. It polls EDGAR's "latest filings" Atom feed, dedupes
entries it has already seen, maps each filing's CIK to a ticker using SEC's
official company_tickers.json, and normalizes into our Event schema.

SEC requires a descriptive User-Agent on every request (see their fair-access
policy) and rate-limits to ~10 req/s. We poll gently.
"""
from __future__ import annotations

import asyncio
import re
from typing import AsyncIterator
from xml.etree import ElementTree as ET

import httpx

from app.schema import Event
from app.sources.base import SourceAdapter

# SEC asks that the User-Agent identify you. Set a real contact before deploying.
USER_AGENT = "MarketIntel/0.2 (contact: akhtarzahir@gmail.com)"

CURRENT_FEED = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=&company=&dateb=&owner=include&count={count}&output=atom"
)
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

_ATOM = "{http://www.w3.org/2005/Atom}"

# "10-K - Apple Inc. (0000320193) (Filer)"  ->  form, company, cik
# Split on " - " (spaces around the dash); form codes like 8-K contain their own dash.
_TITLE_RE = re.compile(r"^\s*(?P<form>.+?)\s+-\s+(?P<company>.+?)\s*\((?P<cik>\d{1,10})\)")


class SecEdgarSource(SourceAdapter):
    name = "edgar"

    def __init__(self, poll_interval: float = 30.0, count: int = 40):
        self.poll_interval = poll_interval
        self.count = count
        self._seen: set[str] = set()
        self._cik_to_ticker: dict[int, str] = {}
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
                timeout=20.0,
            )
        return self._client

    async def _load_ticker_map(self) -> None:
        """Build CIK -> ticker from SEC's official mapping (real entity resolution)."""
        try:
            client = await self._ensure_client()
            r = await client.get(TICKERS_URL)
            r.raise_for_status()
            data = r.json()
            for row in data.values():
                self._cik_to_ticker[int(row["cik_str"])] = row["ticker"]
        except Exception as exc:  # noqa: BLE001 - degrade gracefully, never crash ingest
            print(f"[edgar] could not load ticker map ({exc}); filings will lack tickers")

    def _ticker_for(self, cik: str) -> list[str]:
        t = self._cik_to_ticker.get(int(cik))
        return [t] if t else []

    def _parse_feed(self, xml_text: str) -> list[Event]:
        out: list[Event] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            print(f"[edgar] feed parse error: {exc}")
            return out

        for entry in root.findall(f"{_ATOM}entry"):
            entry_id = (entry.findtext(f"{_ATOM}id") or "").strip()
            if not entry_id or entry_id in self._seen:
                continue
            self._seen.add(entry_id)

            title = (entry.findtext(f"{_ATOM}title") or "").strip()
            updated = (entry.findtext(f"{_ATOM}updated") or "").strip()
            summary = (entry.findtext(f"{_ATOM}summary") or "").strip()
            link_el = entry.find(f"{_ATOM}link")
            url = link_el.get("href") if link_el is not None else ""

            company, form, cik = "", "", ""
            m = _TITLE_RE.match(title)
            if m:
                form = m.group("form").strip()
                company = m.group("company").strip()
                cik = m.group("cik").strip()

            ev = Event(
                id=entry_id,
                source=self.name,
                type="filing",
                title=title,
                body=summary,
                url=url,
                tickers=self._ticker_for(cik) if cik else [],
                entities=[company] if company else [],
                raw={"form": form, "company": company, "cik": cik, "updated": updated},
            )
            out.append(ev)
        return out

    async def events(self) -> AsyncIterator[Event]:
        await self._load_ticker_map()
        client = await self._ensure_client()
        url = CURRENT_FEED.format(count=self.count)

        while True:
            try:
                r = await client.get(url)
                r.raise_for_status()
                for ev in self._parse_feed(r.text):
                    yield ev
            except Exception as exc:  # noqa: BLE001 - one bad poll shouldn't kill the source
                print(f"[edgar] poll failed: {exc}")
            await asyncio.sleep(self.poll_interval)
