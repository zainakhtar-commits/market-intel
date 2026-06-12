"""The processing pipeline: one function that enriches a raw Event in place.

Order matters: resolve entities -> score sentiment -> score materiality
(materiality reads sentiment) -> summarize. Each stage is swappable.
"""
from __future__ import annotations

from app.processing import entity, materiality, sentiment
from app.schema import Event


def _summarize(event: Event) -> str:
    """Baseline extractive summary. Milestone 4: grounded LLM summary w/ citation."""
    body = event.body.strip() or event.title.strip()
    first = body.split(". ")[0]
    return (first[:200] + "…") if len(first) > 200 else first


def process(event: Event) -> Event:
    event = entity.resolve(event)
    event.sentiment = sentiment.score(f"{event.title} {event.body}")
    event.materiality = materiality.score(event)
    event.summary = _summarize(event)
    return event
