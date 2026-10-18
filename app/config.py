"""Runtime config via environment variables (12-factor style)."""
from __future__ import annotations

import os


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


# Tickers the news source follows and the dashboard watches by default.
DEFAULT_TICKERS = [t.strip().upper() for t in os.getenv(
    "TICKERS", "AAPL,MSFT,NVDA,TSLA,AMZN,GOOGL,META"
).split(",") if t.strip()]

# Sources. All real by default; mock is an offline-demo fallback, off by default.
ENABLE_EDGAR = _flag("ENABLE_EDGAR", True)    # real SEC filings
ENABLE_NEWS = _flag("ENABLE_NEWS", True)      # real Google News
ENABLE_MOCK = _flag("ENABLE_MOCK", False)     # synthetic demo filler

EDGAR_POLL_SECONDS = float(os.getenv("EDGAR_POLL_SECONDS", "30"))
NEWS_POLL_SECONDS = float(os.getenv("NEWS_POLL_SECONDS", "90"))
MOCK_INTERVAL_SECONDS = float(os.getenv("MOCK_INTERVAL_SECONDS", "3"))
STORE_MAXLEN = int(os.getenv("STORE_MAXLEN", "5000"))
