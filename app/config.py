"""Runtime config via environment variables (12-factor style)."""
from __future__ import annotations

import os


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


# Which sources to run. EDGAR is real; mock keeps a demo flowing with no internet.
ENABLE_EDGAR = _flag("ENABLE_EDGAR", True)
ENABLE_MOCK = _flag("ENABLE_MOCK", True)

EDGAR_POLL_SECONDS = float(os.getenv("EDGAR_POLL_SECONDS", "30"))
MOCK_INTERVAL_SECONDS = float(os.getenv("MOCK_INTERVAL_SECONDS", "3"))
STORE_MAXLEN = int(os.getenv("STORE_MAXLEN", "5000"))
