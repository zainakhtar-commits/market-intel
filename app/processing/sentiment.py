"""Sentiment — HONEST BASELINE (lexicon).

This is deliberately a simple, transparent baseline so the pipeline is complete
and testable with zero dependencies. Milestone 4 swaps this for an LLM/ML model
behind the same `score()` signature — nothing else changes.
"""
from __future__ import annotations

_POS = {
    "beat", "beats", "rose", "rise", "growth", "record", "surge", "strong",
    "above", "upgrade", "gain", "gains", "profit", "expand", "acquire", "wins",
}
_NEG = {
    "miss", "misses", "fell", "fall", "decline", "cut", "weak", "below",
    "downgrade", "loss", "losses", "lawsuit", "probe", "recall", "warning",
    "softer", "bankruptcy", "fraud", "delay",
}


def score(text: str) -> float:
    """Return sentiment in [-1, 1]."""
    if not text:
        return 0.0
    words = [w.strip(".,!?:;()").lower() for w in text.split()]
    pos = sum(w in _POS for w in words)
    neg = sum(w in _NEG for w in words)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 3)
