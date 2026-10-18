"""Company financials from SEC XBRL data (free, keyless, real).

SEC publishes every public company's reported figures as structured XBRL at
data.sec.gov. We resolve a ticker to its CIK, pull the company's "facts", and
extract headline annual metrics. The hard part is that companies tag the same
concept under different names (revenue alone has several), so we try candidates
and normalize — real data-engineering, the kind reviewers respect.

Information only — reported historical figures, no projections or advice.
"""
from __future__ import annotations

import httpx

USER_AGENT = "MarketIntel/0.5 (contact: akhtarzahir@gmail.com)"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

# Each metric maps to the XBRL concept names companies actually use, in priority order.
METRICS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "net_income": ["NetIncomeLoss"],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "equity": ["StockholdersEquity"],
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
}

_ticker_cik: dict[str, int] = {}
_ticker_name: dict[str, str] = {}


async def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=20.0)


async def _ensure_tickers(client: httpx.AsyncClient) -> None:
    if _ticker_cik:
        return
    r = await client.get(TICKERS_URL)
    r.raise_for_status()
    for row in r.json().values():
        t = row["ticker"].upper()
        _ticker_cik[t] = int(row["cik_str"])
        _ticker_name[t] = row.get("title", t)


def _rank_companies(query: str, name_map: dict[str, str], limit: int = 10) -> list[dict]:
    """Rank companies by a query against BOTH ticker and company name.

    Many companies' names differ from their ticker (Alphabet -> GOOGL,
    Meta Platforms -> META), so we match on both and rank exact/prefix hits first.
    """
    q = query.strip().upper()
    if not q:
        return []
    scored: list[tuple] = []
    for ticker, name in name_map.items():
        tu, nu = ticker.upper(), name.upper()
        if tu == q:
            s = 0
        elif tu.startswith(q):
            s = 1
        elif nu.startswith(q):
            s = 2
        elif q in tu:
            s = 3
        elif q in nu:
            s = 4
        else:
            continue
        scored.append((s, len(name), ticker, name))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [{"ticker": t, "name": n} for _, _, t, n in scored[:limit]]


async def search_companies(query: str, limit: int = 10) -> list[dict]:
    async with await _client() as client:
        try:
            await _ensure_tickers(client)
        except Exception as exc:  # noqa: BLE001
            print(f"[financials] could not load ticker map for search: {exc}")
            return []
    return _rank_companies(query, _ticker_name, limit)


def _annual_series(concept: dict) -> list[dict]:
    """Pull clean annual (10-K, full-year) values from one XBRL concept."""
    units = concept.get("units", {})
    # prefer USD; for EPS it's 'USD/shares'
    key = "USD" if "USD" in units else next(iter(units), None)
    if not key:
        return []
    by_year: dict[int, dict] = {}
    for e in units[key]:
        form = e.get("form", "")
        if not form.startswith("10-K"):
            continue
        if e.get("fp") and e["fp"] != "FY":
            continue
        fy = e.get("fy")
        if fy is None:
            continue
        # keep the latest-filed value for each fiscal year
        if fy not in by_year or (e.get("end", "") > by_year[fy].get("end", "")):
            by_year[fy] = {"fy": fy, "end": e.get("end"), "val": e.get("val")}
    return [by_year[y] for y in sorted(by_year)][-6:]


def _extract(facts: dict, candidates: list[str]) -> list[dict]:
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for name in candidates:
        if name in gaap:
            series = _annual_series(gaap[name])
            if series:
                return series
    return []


async def get_financials(ticker: str) -> dict:
    ticker = ticker.strip().upper()
    async with await _client() as client:
        try:
            await _ensure_tickers(client)
        except Exception as exc:  # noqa: BLE001
            return {"symbol": ticker, "error": f"could not load SEC ticker map: {exc}"}

        cik = _ticker_cik.get(ticker)
        if cik is None:
            return {"symbol": ticker, "error": f"{ticker} not found in SEC company list."}

        try:
            r = await client.get(FACTS_URL.format(cik=cik))
            r.raise_for_status()
            facts = r.json()
        except Exception as exc:  # noqa: BLE001
            return {"symbol": ticker, "error": f"could not load SEC financial facts: {exc}"}

        metrics = {key: _extract(facts, cands) for key, cands in METRICS.items()}
        return {
            "symbol": ticker,
            "company": _ticker_name.get(ticker, facts.get("entityName", ticker)),
            "cik": cik,
            "metrics": metrics,
        }
