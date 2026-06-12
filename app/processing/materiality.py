"""Materiality ranking — HONEST BASELINE (rules).

How likely is this item to actually move/matter for a company? An 8-K (material
event) outranks a routine ownership form; an acquisition headline outranks a
blog post. Transparent rules now; an ML ranker later (Milestone 4), same
`score()` signature.
"""
from __future__ import annotations

from app.schema import Event

# SEC form -> base materiality. 8-K exists specifically to report material events.
_FORM_WEIGHTS = {
    "8-K": 0.80, "8-K/A": 0.80,
    "10-K": 0.65, "10-K/A": 0.65,
    "10-Q": 0.55,
    "S-1": 0.60, "S-4": 0.55,
    "SC 13D": 0.70, "SC 13G": 0.45,
    "DEF 14A": 0.40,
    "4": 0.25, "3": 0.20, "5": 0.20,  # insider ownership forms
}
_KEYWORDS = {
    "acquisition": 0.25, "acquire": 0.25, "merger": 0.25, "bankruptcy": 0.30,
    "guidance": 0.20, "earnings": 0.15, "lawsuit": 0.20, "ceo": 0.15,
    "resign": 0.20, "recall": 0.20, "investigation": 0.20, "probe": 0.20,
}


def score(event: Event) -> float:
    base = 0.30
    if event.type == "filing":
        form = (event.raw.get("form") or "").strip()
        base = _FORM_WEIGHTS.get(form, 0.35)
    elif event.type == "news":
        base = 0.40

    text = f"{event.title} {event.body}".lower()
    bump = sum(w for kw, w in _KEYWORDS.items() if kw in text)

    # Sharp sentiment (either direction) is itself a materiality signal.
    bump += min(abs(event.sentiment) * 0.15, 0.15)

    return round(min(base + bump, 1.0), 3)
