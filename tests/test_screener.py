"""Tests the screener factor math (offline, deterministic)."""
import pytest

from app.screener import _metrics, _style_score, screen, DEFAULT_UNIVERSE


def test_metrics_growth_and_labels():
    # steadily rising series -> positive returns, classified as growth
    closes = [100 * (1.01 ** i) for i in range(80)]  # ~1%/day compounding
    m = _metrics(closes)
    assert m["return_3m"] > 0
    assert m["growth_label"] == "Fast"
    assert m["risk_label"] == "Low"          # zero-noise series -> low volatility


def test_metrics_volatility_detected():
    # alternating jumps -> high volatility
    closes = []
    for i in range(80):
        closes.append(100 + (20 if i % 2 == 0 else -20))
    m = _metrics(closes)
    assert m["volatility"] > 45
    assert m["risk_label"] == "High"


def test_metrics_too_short_returns_none():
    assert _metrics([100, 101, 102]) is None


def test_style_score_ordering():
    fast = {"return_3m": 40.0, "return_1m": 10.0, "volatility": 60.0}
    slow = {"return_3m": 5.0, "return_1m": 1.0, "volatility": 12.0}
    # fast_growth prefers the high-return name
    assert _style_score(fast, "fast_growth") > _style_score(slow, "fast_growth")
    # steady prefers the low-volatility name
    assert _style_score(slow, "steady") > _style_score(fast, "steady")


@pytest.mark.asyncio
async def test_screen_ranks_by_style(monkeypatch):
    import app.screener as sc

    async def fake_history(symbol, days=90):
        # AAAA: strong steady growth; BBBB: flat & volatile
        if symbol == "AAAA":
            return [{"date": str(i), "close": 100 * (1.02 ** i)} for i in range(80)]
        return [{"date": str(i), "close": 100 + (15 if i % 2 else -15)} for i in range(80)]

    monkeypatch.setattr(sc, "get_history", fake_history)
    rows = await screen(universe=["AAAA", "BBBB"], style="fast_growth")
    assert rows[0]["symbol"] == "AAAA"   # growth name ranks first
    assert {"symbol", "return_3m", "volatility", "growth_label", "risk_label", "score"} <= set(rows[0])


def test_default_universe_nonempty():
    assert len(DEFAULT_UNIVERSE) >= 10
