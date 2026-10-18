"""FastAPI app: REST for querying stored events + WebSocket for the live feed.

Run:  uvicorn app.api.main:app --reload
Then: GET http://localhost:8000/events?min_materiality=0.5
      WS  ws://localhost:8000/ws/events
"""
from __future__ import annotations

import asyncio
import contextlib
import os
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app import config
from app.engine import Engine
from app.market import get_quotes, get_history, diagnose
from app.paper import PaperBroker, TradeError
from app.alerts import AlertStore
from app.finance import FinanceStore, parse_csv, sample_transactions, parse_statement_text, extract_pdf_text
from app.screener import screen
from app import tax as taxmod
from app.financials import get_financials, search_companies
from app.earnings import get_earnings, get_upcoming
from app.opportunities import find_opportunities, SCREENS
from app.signals import rate as rate_signal
from app.schema import Event
from app.sources import MockSource, SecEdgarSource, GoogleNewsSource
from app.store import EventStore

_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "static")
_INDEX = os.path.abspath(os.path.join(_STATIC_DIR, "index.html"))

# Default watchlist for the dashboard (user-editable in the UI).
DEFAULT_WATCHLIST = config.DEFAULT_TICKERS
# Major US indices for the markets strip (Yahoo symbols).
INDICES = [("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("^DJI", "Dow Jones")]

store = EventStore(maxlen=config.STORE_MAXLEN)

_PORTFOLIO_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "paper_portfolio.json")
broker = PaperBroker(path=os.path.abspath(_PORTFOLIO_PATH))


_ALERTS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "alerts.json")
alert_store = AlertStore(path=os.path.abspath(_ALERTS_PATH))

_FINANCE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "finance_data.json")
finance_store = FinanceStore(path=os.path.abspath(_FINANCE_PATH))


class OrderRequest(BaseModel):
    ticker: str
    side: str            # "buy" | "sell"
    shares: float


class AlertRequest(BaseModel):
    ticker: str
    direction: str       # "above" | "below"
    price: float
    action: str = "notify"   # "notify" | "buy" | "sell"
    shares: float = 0


class AccountRequest(BaseModel):
    name: str
    type: str            # checking|savings|cash|investment|credit|loan
    balance: float


class ImportRequest(BaseModel):
    content: str         # raw CSV text


def _build_sources() -> list:
    sources: list = []
    if config.ENABLE_EDGAR:
        sources.append(SecEdgarSource(poll_interval=config.EDGAR_POLL_SECONDS))
    if config.ENABLE_NEWS:
        sources.append(GoogleNewsSource(
            tickers=config.DEFAULT_TICKERS, poll_interval=config.NEWS_POLL_SECONDS))
    if config.ENABLE_MOCK:
        sources.append(MockSource(interval=config.MOCK_INTERVAL_SECONDS))
    return sources


engine = Engine(_build_sources(), store)


async def _alert_loop():
    """Periodically check live prices against active alerts and fire matching rules."""
    while True:
        await asyncio.sleep(20)
        try:
            tickers = alert_store.active_tickers()
            if not tickers:
                continue
            quotes = await get_quotes(tickers)
            prices = {q["symbol"]: q.get("price") for q in quotes}
            alert_store.check(prices, broker=broker)
        except Exception as exc:  # noqa: BLE001
            print(f"[alerts] check loop error: {exc}")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    await engine.start()
    alert_task = asyncio.create_task(_alert_loop())
    yield
    alert_task.cancel()
    await engine.stop()


app = FastAPI(title="Market Intel", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def dashboard() -> FileResponse:
    """Serve the single-file dashboard."""
    return FileResponse(_INDEX)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "stored_events": len(store), "sources": [s.name for s in engine.sources]}


@app.get("/quote")
async def quote(symbols: str = ",".join(DEFAULT_WATCHLIST)) -> dict[str, Any]:
    """Latest quotes for a comma-separated list of tickers (free Stooq feed).

    Information only — returns prices, not recommendations.
    """
    tickers = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    quotes = await get_quotes(tickers)
    return {"count": len(quotes), "quotes": quotes}


@app.get("/history")
async def history(symbol: str, days: int = 30) -> dict[str, Any]:
    """Recent daily closes for one ticker (sparklines / charts)."""
    data = await get_history(symbol, days=days)
    return {"symbol": symbol.upper(), "points": data}


@app.get("/markets")
async def markets() -> dict[str, Any]:
    """Quotes for the major US indices (markets strip)."""
    quotes = await get_quotes([sym for sym, _ in INDICES])
    names = dict(INDICES)
    for q in quotes:
        q["name"] = names.get(q["symbol"], q["symbol"])
    return {"indices": quotes}


@app.get("/diag")
async def diag(symbol: str = "AAPL") -> dict[str, Any]:
    """Live-test the market-data providers. Open in a browser to see why data may be missing."""
    return await diagnose(symbol)


@app.get("/search")
async def search(q: str, limit: int = 10) -> dict[str, Any]:
    """Typeahead company search by name or ticker (SEC company list)."""
    return {"results": await search_companies(q, limit=limit)}


@app.get("/financials")
async def financials(symbol: str) -> dict[str, Any]:
    """Reported annual financials for a company, from SEC XBRL data. Information only."""
    return await get_financials(symbol)


@app.get("/screen")
async def screen_stocks(style: str = "balanced", universe: str | None = None) -> dict[str, Any]:
    """Rank stocks by growth/risk characteristics for a chosen style.

    Information & analysis only — surfaces stocks matching the selected
    characteristics; it is NOT investment advice and recommends nothing.
    """
    syms = [s.strip().upper() for s in universe.split(",")] if universe else None
    rows = await screen(universe=syms, style=style)
    return {
        "style": style,
        "disclaimer": "Information and analysis only. Not investment advice. You decide.",
        "count": len(rows),
        "results": rows,
    }


@app.get("/earnings")
async def earnings(symbol: str) -> dict[str, Any]:
    """Latest reported revenue, net income and EPS with YoY growth, from SEC filings. Information only."""
    return await get_earnings(symbol)


@app.get("/earnings/upcoming")
async def upcoming_earnings(symbols: str | None = None) -> dict[str, Any]:
    """Estimated upcoming report windows for a set of tickers (defaults to the dashboard watchlist)."""
    syms = [x.strip().upper() for x in symbols.split(",")] if symbols else list(DEFAULT_WATCHLIST)
    return await get_upcoming(syms)


@app.get("/opportunities")
async def opportunities(screen: str = "momentum", universe: str | None = None, limit: int = 10) -> dict[str, Any]:
    """Potential-buy ideas from a transparent screen. Information & analysis only - not investment advice."""
    syms = [x.strip().upper() for x in universe.split(",")] if universe else None
    return await find_opportunities(universe=syms, screen_name=screen, limit=limit)


@app.get("/signal")
async def signal(symbol: str) -> dict[str, Any]:
    """Transparent rules-based signal (Strong Buy ... Strong Sell) from momentum + volatility. Not advice."""
    rows = await screen(universe=[symbol.strip().upper()], style="balanced")
    if not rows:
        return {"symbol": symbol.strip().upper(), "error": "No price data available."}
    m = rows[0]
    sig = rate_signal(m.get("return_3m"), m.get("volatility"), m.get("risk_label"))
    return {
        "symbol": m["symbol"], "price": m.get("price"), **sig,
        "metrics": {"return_1m": m.get("return_1m"), "return_3m": m.get("return_3m"), "volatility": m.get("volatility")},
        "disclaimer": "Transparent rules-based signal from momentum & volatility only - NOT investment advice or a recommendation. You decide.",
    }


# --- Paper trading (simulation only — no real money, no real orders) -------
@app.get("/portfolio")
async def portfolio() -> dict[str, Any]:
    """Current paper portfolio, valued at live market prices."""
    return await broker.snapshot()


@app.post("/order")
async def place_order(req: OrderRequest) -> Any:
    """Place a simulated market order at the current price. Not investment advice."""
    quotes = await get_quotes([req.ticker])
    price = quotes[0].get("price") if quotes else None
    if not price:
        return JSONResponse(
            status_code=400,
            content={"error": f"No market price available for {req.ticker.upper()} (is the quote feed reachable?)."},
        )
    try:
        order = broker.execute(req.ticker, req.side, req.shares, price)
    except TradeError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    snapshot = await broker.snapshot()
    return {"order": order, "portfolio": snapshot}


@app.post("/portfolio/reset")
async def reset_portfolio() -> dict[str, Any]:
    """Reset to the starting virtual cash balance."""
    broker.reset()
    return await broker.snapshot()


# --- Price alerts & conditional simulated orders (user-defined rules) -------
@app.get("/alerts")
async def get_alerts() -> dict[str, Any]:
    return alert_store.snapshot()


@app.post("/alerts")
async def create_alert(req: AlertRequest) -> Any:
    try:
        alert = alert_store.add(req.ticker, req.direction, req.price, req.action, req.shares)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    return {"alert": alert}


@app.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: int) -> dict[str, Any]:
    return {"removed": alert_store.remove(alert_id)}


@app.post("/alerts/clear_triggered")
async def clear_triggered_alerts() -> dict[str, Any]:
    alert_store.clear_triggered()
    return alert_store.snapshot()


# --- Personal finance (fully local; no bank connections; not financial advice) ---
@app.get("/finance")
async def finance() -> dict[str, Any]:
    return finance_store.snapshot()


@app.post("/finance/accounts")
async def add_account(req: AccountRequest) -> dict[str, Any]:
    finance_store.add_account(req.name, req.type, req.balance)
    return finance_store.snapshot()


@app.delete("/finance/accounts/{acc_id}")
async def remove_account(acc_id: int) -> dict[str, Any]:
    finance_store.remove_account(acc_id)
    return finance_store.snapshot()


@app.post("/finance/import")
async def import_transactions(req: ImportRequest) -> Any:
    rows = parse_csv(req.content)
    if not rows:
        return JSONResponse(status_code=400, content={
            "error": "No transactions found. Expected a CSV with date, description, and amount (or debit/credit) columns."})
    finance_store.import_rows(rows)
    return {"imported": len(rows), **finance_store.snapshot()}


@app.post("/finance/import_file")
async def import_file(file: UploadFile = File(...)) -> Any:
    """Import a CSV or PDF statement. PDF parsing is best-effort."""
    data = await file.read()
    name = (file.filename or "").lower()
    try:
        if name.endswith(".pdf"):
            rows = parse_statement_text(extract_pdf_text(data))
        else:
            rows = parse_csv(data.decode("utf-8", errors="ignore"))
    except RuntimeError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    if not rows:
        return JSONResponse(status_code=400, content={
            "error": "Couldn't find transactions in that file. CSV works best; PDF layouts vary."})
    finance_store.import_rows(rows)
    return {"imported": len(rows), **finance_store.snapshot()}


@app.post("/finance/sample")
async def load_sample() -> dict[str, Any]:
    finance_store.import_rows(sample_transactions())
    return finance_store.snapshot()


@app.get("/tax")
async def tax(income: float, status: str = "single",
              deduction: float | None = None, fica: bool = True) -> dict[str, Any]:
    """Estimate 2026 federal income tax + FICA. Estimate only, not tax advice."""
    return taxmod.estimate(income, status=status, deduction=deduction, include_fica=fica)


@app.post("/finance/clear")
async def clear_finance() -> dict[str, Any]:
    finance_store.clear_transactions()
    return finance_store.snapshot()


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
