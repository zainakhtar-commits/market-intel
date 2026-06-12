"""FastAPI app: REST for querying stored events + WebSocket for the live feed.

Run:  uvicorn app.api.main:app --reload
Then: GET http://localhost:8000/events?min_materiality=0.5
      WS  ws://localhost:8000/ws/events
"""
from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.engine import Engine
from app.schema import Event
from app.sources import MockSource, SecEdgarSource
from app.store import EventStore

store = EventStore(maxlen=config.STORE_MAXLEN)


def _build_sources() -> list:
    sources: list = []
    if config.ENABLE_EDGAR:
        sources.append(SecEdgarSource(poll_interval=config.EDGAR_POLL_SECONDS))
    if config.ENABLE_MOCK:
        sources.append(MockSource(interval=config.MOCK_INTERVAL_SECONDS))
    return sources


engine = Engine(_build_sources(), store)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    await engine.start()
    yield
    await engine.stop()


app = FastAPI(title="Market Intel", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "stored_events": len(store), "sources": [s.name for s in engine.sources]}


@app.get("/events")
async def events(
    ticker: str | None = None,
    source: str | None = None,
    min_materiality: float = 0.0,
    limit: int = 100,
) -> dict[str, Any]:
    """Query stored events. This is the dashboard's main data source."""
    results = store.query(
        ticker=ticker, source=source, min_materiality=min_materiality, limit=limit
    )
    return {"count": len(results), "events": [e.model_dump(mode="json") for e in results]}


@app.websocket("/ws/events")
async def ws_events(ws: WebSocket) -> None:
    """Push every newly processed event to the client in real time."""
    await ws.accept()
    queue: asyncio.Queue[Event] = asyncio.Queue()

    async def on_event(ev: Event) -> None:
        await queue.put(ev)

    engine.subscribe(on_event)
    try:
        while True:
            ev = await queue.get()
            await ws.send_json(ev.model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
    finally:
        engine.unsubscribe(on_event)
