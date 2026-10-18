"""Tests the earnings-highlights reducer (offline, deterministic)."""
import pytest

from app.earnings import summarize, _yoy, _fmt_usd, get_earnings


def test_yoy_growth():
    assert _yoy([{"val": 100}, {"val": 120}]) == 20.0
    assert _yoy([{"val": 0}, {"val": 120}]) is None   # divide-by-zero guard
    assert _yoy([{"val": 100}]) is None               # need two points


def test_fmt_usd():
    assert _fmt_usd(2_500_000_000) == "$2.50B"
    assert _fmt_usd(3_400_000) == "$3.4M"
    assert _fmt_usd(None) is None


def test_summarize_builds_highlights():
    fin = {"symbol": "AAPL", "company": "Apple Inc.", "metrics": {
        "revenue": [{"fy": 2023, "val": 383_000_000_000}, {"fy": 2024, "val": 400_000_000_000}],
        "net_income": [{"fy": 2023, "val": 97_000_000_000}, {"fy": 2024, "val": 100_000_000_000}],
        "eps": [{"fy": 2023, "val": 6.13}, {"fy": 2024, "val": 6.50}],
    }}
    out = summarize(fin)
    assert out["symbol"] == "AAPL"
    assert out["fiscal_year"] == 2024
    assert out["revenue"]["yoy_growth_pct"] == round((400 / 383 - 1) * 100, 1)
    assert out["revenue"]["display"] == "$400.00B"
    assert out["revenue_trend"] == "Growing"
    assert len(out["history"]["eps"]) == 2


def test_summarize_passes_error_through():
    assert summarize({"symbol": "ZZZ", "error": "not found"})["error"] == "not found"


@pytest.mark.asyncio
async def test_get_earnings_monkeypatched(monkeypatch):
    import app.earnings as em

    async def fake_fin(symbol):
        return {"symbol": symbol, "company": "X Corp", "metrics": {"revenue": [{"fy": 2024, "val": 1000}]}}

    monkeypatch.setattr(em, "get_financials", fake_fin)
    out = await get_earnings("X")
    assert out["symbol"] == "X" and out["fiscal_year"] == 2024


def test_estimate_next_report():
    from app.earnings import estimate_next_report
    assert estimate_next_report("2024-09-28") == "2025-09-28"
    assert estimate_next_report(None) is None
    assert estimate_next_report("garbage") is None


@pytest.mark.asyncio
async def test_get_upcoming_sorts_and_shapes(monkeypatch):
    import app.earnings as em

    async def fake_fin(symbol):
        ends = {"A": "2024-12-31", "B": "2024-03-31"}
        return {"symbol": symbol, "company": symbol + " Inc",
                "metrics": {"revenue": [{"fy": 2024, "end": ends[symbol], "val": 100}]}}

    monkeypatch.setattr(em, "get_financials", fake_fin)
    from app.earnings import get_upcoming
    out = await get_upcoming(["A", "B"])
    assert out["count"] == 2
    # B's period ends sooner -> its estimated next report is sooner -> listed first
    assert out["upcoming"][0]["symbol"] == "B"
    assert out["upcoming"][0]["estimated_next_report"] == "2025-03-31"
