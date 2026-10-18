"""Earnings highlights — latest reported revenue, net income and EPS with
year-over-year growth, plus an *estimated* next-report window, pulled from the
same SEC XBRL facts the financials module uses. Information only; these are
reported annual figures, not forward estimates and not investment advice.
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta

from app.financials import get_financials


def _yoy(series: list[dict]) -> float | None:
    """Year-over-year growth % between the last two annual values."""
    if len(series) < 2:
        return None
    prev = series[-2].get("val")
    cur = series[-1].get("val")
    if not prev or cur is None or prev == 0:
        return None
    return round((cur / prev - 1) * 100, 1)


def _fmt_usd(v: float | None) -> str | None:
    if v is None:
        return None
    a = abs(v)
    if a >= 1e9:
        return f"${v / 1e9:.2f}B"
    if a >= 1e6:
        return f"${v / 1e6:.1f}M"
    return f"${v:,.0f}"


def _trend(growth: float | None) -> str:
    if growth is None:
        return "n/a"
    if growth > 1:
        return "Growing"
    if growth < -1:
        return "Declining"
    return "Flat"


def estimate_next_report(last_end: str | None) -> str | None:
    """Estimate the next annual-report date as ~1 year after the last period end.
    Approximate only — companies file on their own schedules.
    """
    if not last_end:
        return None
    try:
        y, m, d = (int(x) for x in last_end.split("-"))
        return (date(y, m, d) + timedelta(days=365)).isoformat()
    except Exception:
        return None


def summarize(fin: dict) -> dict:
    """Build the earnings summary from a financials payload (pure, testable)."""
    if fin.get("error"):
        return {"symbol": fin.get("symbol"), "error": fin["error"]}

    m = fin.get("metrics", {}) or {}
    rev = m.get("revenue", []) or []
    ni = m.get("net_income", []) or []
    eps = m.get("eps", []) or []

    latest_fy = (rev[-1]["fy"] if rev else (ni[-1]["fy"] if ni else None))
    last_end = (rev[-1].get("end") if rev else (ni[-1].get("end") if ni else None))
    rev_g = _yoy(rev)

    return {
        "symbol": fin.get("symbol"),
        "company": fin.get("company"),
        "fiscal_year": latest_fy,
        "last_period_end": last_end,
        "estimated_next_report": estimate_next_report(last_end),
        "disclaimer": "Reported annual figures from SEC filings. Estimated next-report date is approximate. Information only, not investment advice.",
        "revenue": {
            "latest": rev[-1]["val"] if rev else None,
            "display": _fmt_usd(rev[-1]["val"]) if rev else None,
            "yoy_growth_pct": rev_g,
        },
        "net_income": {
            "latest": ni[-1]["val"] if ni else None,
            "display": _fmt_usd(ni[-1]["val"]) if ni else None,
            "yoy_growth_pct": _yoy(ni),
        },
        "eps": {
            "latest": eps[-1]["val"] if eps else None,
            "yoy_growth_pct": _yoy(eps),
        },
        "revenue_trend": _trend(rev_g),
        "history": {
            "revenue": [{"fy": r["fy"], "val": r["val"]} for r in rev],
            "net_income": [{"fy": r["fy"], "val": r["val"]} for r in ni],
            "eps": [{"fy": r["fy"], "val": r["val"]} for r in eps],
        },
    }


async def get_earnings(symbol: str) -> dict:
    """Fetch SEC financials for a ticker and reduce them to earnings highlights."""
    fin = await get_financials(symbol)
    return summarize(fin)


async def get_upcoming(symbols: list[str]) -> dict:
    """Estimated upcoming (next) report windows for a list of tickers, soonest first."""
    summaries = await asyncio.gather(*[get_earnings(s) for s in symbols])
    rows = []
    for e in summaries:
        if e.get("error"):
            rows.append({"symbol": e.get("symbol"), "error": e["error"]})
            continue
        rows.append({
            "symbol": e.get("symbol"),
            "company": e.get("company"),
            "last_fiscal_year": e.get("fiscal_year"),
            "last_period_end": e.get("last_period_end"),
            "estimated_next_report": e.get("estimated_next_report"),
            "revenue_trend": e.get("revenue_trend"),
        })
    rows.sort(key=lambda r: r.get("estimated_next_report") or "9999-99-99")
    return {
        "disclaimer": "Estimated from the most recent SEC filing (~1 year cadence) — approximate, not official announcement dates.",
        "count": len(rows),
        "upcoming": rows,
    }
