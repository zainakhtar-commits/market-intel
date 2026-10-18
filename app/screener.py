"""Factor screener — classify and rank stocks by growth and risk.

This is an information/analysis tool, NOT investment advice. It computes two
transparent, well-known factors from price history:

  • growth  = trailing return (how fast the price has been rising)
  • risk    = annualized volatility (how much it bounces around)

Then it labels each stock and ranks a universe by a style the *user* chooses.
It surfaces stocks that match the selected characteristics; it never tells the
user what to buy, and the criteria are fully visible so the user decides.
"""
from __future__ import annotations

import asyncio
import math
import statistics

from app.market import get_history

TRADING_DAYS = 252

# A varied default universe (mix of fast-growth and steady names) so styles differ.
DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "AMD", "NFLX", "PLTR",
    "JPM", "KO", "PG", "JNJ", "WMT", "XOM", "COST", "DIS", "UBER", "PEP",
]

STYLES = {"fast_growth", "balanced", "steady"}


def _metrics(closes: list[float]) -> dict | None:
    closes = [c for c in closes if c]
    if len(closes) < 20:
        return None
    price = closes[-1]

    def trailing(n: int) -> float | None:
        return round((closes[-1] / closes[-1 - n] - 1) * 100, 2) if len(closes) > n else None

    ret_1m = trailing(21)
    ret_3m = trailing(63) if len(closes) > 63 else trailing(len(closes) - 1)

    daily = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    vol = round(statistics.pstdev(daily) * math.sqrt(TRADING_DAYS) * 100, 2) if len(daily) > 1 else 0.0

    growth_basis = ret_3m if ret_3m is not None else (ret_1m or 0.0)
    growth_label = "Fast" if growth_basis >= 15 else "Moderate" if growth_basis > 0 else "Slow"
    risk_label = "High" if vol >= 45 else "Medium" if vol >= 25 else "Low"

    return {
        "price": round(price, 2),
        "return_1m": ret_1m,
        "return_3m": ret_3m,
        "volatility": vol,
        "growth_label": growth_label,
        "risk_label": risk_label,
    }


def _style_score(m: dict, style: str) -> float:
    g = m["return_3m"] if m["return_3m"] is not None else (m["return_1m"] or 0.0)
    v = m["volatility"] or 0.0001
    if style == "fast_growth":
        return g                       # pure momentum / growth speed
    if style == "steady":
        return -v + g * 0.05           # prioritise low volatility, mild reward for positive trend
    return g / (v + 1)                 # balanced: risk-adjusted return (Sharpe-like proxy)


async def screen(universe: list[str] | None = None, style: str = "balanced", days: int = 90) -> list[dict]:
    universe = (universe or DEFAULT_UNIVERSE)[:40]
    style = style if style in STYLES else "balanced"

    histories = await asyncio.gather(*[get_history(s, days=days) for s in universe])
    rows: list[dict] = []
    for sym, pts in zip(universe, histories):
        m = _metrics([p["close"] for p in pts])
        if not m:
            continue
        rows.append({"symbol": sym.upper(), **m, "score": round(_style_score(m, style), 3)})

    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows
