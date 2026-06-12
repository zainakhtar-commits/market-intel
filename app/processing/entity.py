"""Entity resolution — map free-text mentions to tickers/companies.

EDGAR filings already carry a CIK we resolve precisely; news items don't, so we
do a light lookup against a known-company table. This is the seam where a real
NER + fuzzy-matching model goes later — mapping messy news text to the right
ticker is a genuine NLP problem.
"""
from __future__ import annotations

from app.schema import Event

# Minimal seed table; extend or replace with SEC's full company_tickers.json.
_NAME_TO_TICKER = {
    "apple": "AAPL", "microsoft": "MSFT", "nvidia": "NVDA", "tesla": "TSLA",
    "amazon": "AMZN", "google": "GOOGL", "alphabet": "GOOGL", "meta": "META",
}


def resolve(event: Event) -> Event:
    # Trust precise source-provided tickers (e.g. EDGAR CIK match) first.
    if event.tickers:
        return event

    text = f"{event.title} {event.body}".lower()
    found: list[str] = []
    for name, ticker in _NAME_TO_TICKER.items():
        if name in text and ticker not in found:
            found.append(ticker)
    event.tickers = found
    return event
