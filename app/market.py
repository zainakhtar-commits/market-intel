"""Market-data adapter — Yahoo Finance primary, Stooq fallback (both free/keyless).

Yahoo's chart endpoint returns current price, day OHLCV, and history in one call,
and it's far more reliable than Stooq's CSV (which rate-limits aggressively).
If Yahoo fails for a symbol we fall back to Stooq, and if both fail we return a
descriptive error so the dashboard can show *why* instead of a silent "n/a".

This is a read-only information feed; nothing here recommends trades.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

import httpx

USER_AGENT = "Mozilla/5.0 (Macintosh) MarketIntel/0.5 (contact: akhtarzahir@gmail.com)"

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={rng}&interval={interval}"
STOOQ_QUOTE = "https://stooq.com/q/l/?s={symbols}&f=sd2t2ohlcv&h&e=csv"
STOOQ_HISTORY = "https://stooq.com/q/d/l/?s={symbol}&i=d"

# How many days each chart range needs from Yahoo.
def _range_for_days(days: int) -> str:
    if days <= 7:
        return "5d"
    if days <= 31:
        return "1mo"
    if days <= 93:
        return "3mo"
    if days <= 186:
        return "6mo"
    if days <= 370:
        return "1y"
    return "2y"


def _to_yahoo(sym: str) -> str:
    """Yahoo uses dashes for share classes (BRK.B -> BRK-B); indices keep '^'."""
    sym = sym.strip().upper()
    if sym.startswith("^"):
        return sym
    return sym.replace(".", "-")


def _to_stooq(sym: str) -> str:
    sym = sym.strip().lower()
    if sym.startswith("^") or "." in sym:
        return sym
    return f"{sym}.us"


# kept public name for existing tests
def _to_stooq_symbol(sym: str) -> str:
    return _to_stooq(sym)


def _num(v) -> float | None:
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return None


def _last_valid(seq):
    for x in reversed(seq or []):
        if x is not None:
            return x
    return None


async def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/csv"}, timeout=15.0)


# --------------------------------------------------------------------------- #
# Quotes
# --------------------------------------------------------------------------- #
def _quote_from_yahoo(symbol: str, data: dict) -> dict | None:
    try:
        res = data["chart"]["result"][0]
        meta = res["meta"]
        price = meta.get("regularMarketPrice")
        prev = meta.get("previousClose") or meta.get("chartPreviousClose")
        q = (res.get("indicators", {}).get("quote", [{}]) or [{}])[0]
        ts = res.get("timestamp") or []
        last_dt = datetime.fromtimestamp(ts[-1], tz=timezone.utc) if ts else None
        change = (price - prev) if (price is not None and prev) else None
        change_pct = (change / prev * 100) if (change is not None and prev) else None
        return {
            "symbol": meta.get("symbol", symbol).upper(),
            "price": round(price, 4) if price is not None else None,
            "open": _last_valid(q.get("open")),
            "high": _last_valid(q.get("high")),
            "low": _last_valid(q.get("low")),
            "volume": _last_valid(q.get("volume")),
            "date": last_dt.strftime("%Y-%m-%d") if last_dt else None,
            "time": last_dt.strftime("%H:%M") if last_dt else None,
            "change": round(change, 4) if change is not None else None,
            "change_pct": round(change_pct, 3) if change_pct is not None else None,
        }
    except (KeyError, IndexError, TypeError):
        return None


async def _stooq_quote_batch(client: httpx.AsyncClient, symbols: list[str]) -> dict[str, dict]:
    joined = ",".join(_to_stooq(s) for s in symbols)
    out: dict[str, dict] = {}
    try:
        r = await client.get(STOOQ_QUOTE.format(symbols=joined))
        r.raise_for_status()
        for row in csv.DictReader(io.StringIO(r.text)):
            sym = (row.get("Symbol") or "").upper().replace(".US", "")
            close, open_ = _num(row.get("Close")), _num(row.get("Open"))
            change = round(close - open_, 4) if (close is not None and open_) else None
            out[sym] = {
                "symbol": sym, "price": close, "open": open_,
                "high": _num(row.get("High")), "low": _num(row.get("Low")),
                "volume": _num(row.get("Volume")), "date": row.get("Date"), "time": row.get("Time"),
                "change": change,
                "change_pct": round((close - open_) / open_ * 100, 3) if (close is not None and open_) else None,
            }
    except Exception as exc:  # noqa: BLE001
        print(f"[market] stooq fallback failed: {exc}")
    return out


async def get_quotes(symbols: list[str]) -> list[dict]:
    if not symbols:
        return []
    out: list[dict] = []
    async with await _client() as client:
        need_fallback: list[str] = []
        for s in symbols:
            try:
                r = await client.get(YAHOO_CHART.format(symbol=_to_yahoo(s), rng="5d", interval="1d"))
                r.raise_for_status()
                q = _quote_from_yahoo(s, r.json())
                if q and q.get("price") is not None:
                    out.append(q)
                    continue
                need_fallback.append(s)
            except Exception as exc:  # noqa: BLE001
                print(f"[market] yahoo quote failed for {s}: {exc}")
                need_fallback.append(s)

        if need_fallback:
            fb = await _stooq_quote_batch(client, need_fallback)
            for s in need_fallback:
                key = s.upper().replace(".US", "")
                out.append(fb.get(key) or {"symbol": s.upper(), "price": None,
                                           "error": "unavailable from Yahoo or Stooq"})
    # preserve request order
    order = {s.upper().replace(".", "-"): i for i, s in enumerate(symbols)}
    out.sort(key=lambda q: order.get(q["symbol"].replace(".", "-"), 999))
    return out


# --------------------------------------------------------------------------- #
# History
# --------------------------------------------------------------------------- #
async def get_history(symbol: str, days: int = 30) -> list[dict]:
    async with await _client() as client:
        # Yahoo first
        try:
            r = await client.get(YAHOO_CHART.format(symbol=_to_yahoo(symbol), rng=_range_for_days(days), interval="1d"))
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            ts = res.get("timestamp") or []
            closes = (res.get("indicators", {}).get("quote", [{}]) or [{}])[0].get("close") or []
            rows = []
            for t, c in zip(ts, closes):
                if c is None:
                    continue
                d = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
                rows.append({"date": d, "close": round(c, 4)})
            if rows:
                return rows[-days:]
        except Exception as exc:  # noqa: BLE001
            print(f"[market] yahoo history failed for {symbol}: {exc}")

        # Stooq fallback
        try:
            r = await client.get(STOOQ_HISTORY.format(symbol=_to_stooq(symbol)))
            r.raise_for_status()
            rows = []
            for row in csv.DictReader(io.StringIO(r.text)):
                c = _num(row.get("Close"))
                if c is not None:
                    rows.append({"date": row.get("Date"), "close": c})
            return rows[-days:]
        except Exception as exc:  # noqa: BLE001
            print(f"[market] stooq history failed for {symbol}: {exc}")
    return []


# --------------------------------------------------------------------------- #
# Diagnostics
# --------------------------------------------------------------------------- #
async def diagnose(symbol: str = "AAPL") -> dict:
    """Live-test both providers and report what each returns. Surfaced at /diag."""
    result: dict = {"symbol": symbol.upper()}
    async with await _client() as client:
        try:
            r = await client.get(YAHOO_CHART.format(symbol=_to_yahoo(symbol), rng="5d", interval="1d"))
            q = _quote_from_yahoo(symbol, r.json()) if r.status_code == 200 else None
            result["yahoo"] = {"http_status": r.status_code, "price": (q or {}).get("price"),
                               "ok": bool(q and q.get("price") is not None),
                               "sample": r.text[:160]}
        except Exception as exc:  # noqa: BLE001
            result["yahoo"] = {"error": f"{type(exc).__name__}: {exc}"}
        try:
            r = await client.get(STOOQ_QUOTE.format(symbols=_to_stooq(symbol)))
            result["stooq"] = {"http_status": r.status_code, "sample": r.text[:160]}
        except Exception as exc:  # noqa: BLE001
            result["stooq"] = {"error": f"{type(exc).__name__}: {exc}"}
    return result
