"""The common event schema every source normalizes into.

Keeping one normalized shape is the core design decision: sources are messy and
all different (filings, news, market data), but everything downstream
(pipeline, store, API, frontend) speaks this one language.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Event(BaseModel):
    """A single normalized market-relevant item."""

    id: str = Field(..., description="Stable unique id (source-specific).")
    source: str = Field(..., description="Adapter that produced this, e.g. 'edgar'.")
    type: str = Field(..., description="'filing' | 'news' | 'market' | ...")
    title: str
    body: str = ""
    url: str = ""
    published_at: datetime = Field(default_factory=_utcnow)
    ingested_at: datetime = Field(default_factory=_utcnow)

    # Filled in by the processing pipeline:
    tickers: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    sentiment: float = 0.0  # -1.0 (negative) .. +1.0 (positive)
    materiality: float = 0.0  # 0.0 (routine) .. 1.0 (highly material)
    summary: str | None = None

    # Original payload kept for debugging / future re-processing:
    raw: dict[str, Any] = Field(default_factory=dict)

    def short(self) -> str:
        return f"[{self.source}/{self.type}] {self.title[:80]} (m={self.materiality:.2f})"
