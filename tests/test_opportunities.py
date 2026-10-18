"""Tests the opportunities screens (offline, deterministic)."""
import pytest

from app.opportunities import build, find_opportunities, SCREENS


def _row(sym, r1, r3, vol, risk):
    return {"symbol": sym, "return_1m": r1, "return_3m": r3, "volatility": vol, "risk_label": risk}


def test_momentum_filters_and_adds_reason():
    rows = [
        _row("A", 3, 20, 30, "Medium"),   # passes
        _row("B", 1, 2, 20, "Low"),       # 3m <= 5 -> fail
        _row("C", 0, 40, 60, "High"),     # high risk -> fail
    ]
    ideas = build(rows, "momentum")
    syms = [i["symbol"] for i in ideas]
    assert syms == ["A"]
    assert "reason" in ideas[0]


def test_steady_screen():
    rows = [_row("S", 1, 2, 15, "Low"), _row("V", -1, -5, 18, "Low")]
    assert [i["symbol"] for i in build(rows, "steady")] == ["S"]


def test_value_reversal_screen():
    rows = [_row("R", -6, 10, 25, "Medium"), _row("X", 4, 10, 25, "Medium")]
    assert [i["symbol"] for i in build(rows, "value_reversal")] == ["R"]


def test_limit_is_respected():
    rows = [_row(str(i), 2, 20, 30, "Medium") for i in range(20)]
    assert len(build(rows, "momentum", limit=5)) == 5


def test_all_screens_registered():
    assert {"momentum", "steady", "value_reversal"} <= set(SCREENS)


@pytest.mark.asyncio
async def test_find_opportunities_monkeypatched(monkeypatch):
    import app.opportunities as opp

    async def fake_screen(universe=None, style="balanced", days=90):
        return [_row("AAAA", 2, 25, 28, "Medium"), _row("BBBB", 1, 1, 20, "Low")]

    monkeypatch.setattr(opp, "screen", fake_screen)
    out = await find_opportunities(screen_name="momentum")
    assert out["screen"] == "momentum"
    assert out["count"] == 1 and out["ideas"][0]["symbol"] == "AAAA"
    assert "not investment advice" in out["disclaimer"].lower()
