import os
import tempfile

import pytest

from app.paper import PaperBroker, TradeError, STARTING_CASH


def _broker():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)  # start with no file
    return PaperBroker(path=path)


def test_buy_reduces_cash_and_sets_avg_cost():
    b = _broker()
    b.execute("AAPL", "buy", 10, 100.0)
    assert b.cash == STARTING_CASH - 1000.0
    assert b.positions["AAPL"]["shares"] == 10
    assert b.positions["AAPL"]["avg_cost"] == 100.0


def test_avg_cost_blends_across_buys():
    b = _broker()
    b.execute("AAPL", "buy", 10, 100.0)   # 1000
    b.execute("AAPL", "buy", 10, 200.0)   # 2000
    assert b.positions["AAPL"]["shares"] == 20
    assert b.positions["AAPL"]["avg_cost"] == 150.0  # (1000+2000)/20


def test_insufficient_funds_rejected():
    b = _broker()
    with pytest.raises(TradeError):
        b.execute("AAPL", "buy", 100000, 100.0)  # way over $100k
    assert b.cash == STARTING_CASH  # unchanged


def test_sell_realizes_pnl_and_frees_cash():
    b = _broker()
    b.execute("AAPL", "buy", 10, 100.0)
    b.execute("AAPL", "sell", 10, 130.0)  # +$30/share realized
    assert "AAPL" not in b.positions
    assert b.realized_pnl == pytest.approx(300.0)
    assert b.cash == pytest.approx(STARTING_CASH + 300.0)


def test_cannot_sell_more_than_held():
    b = _broker()
    b.execute("AAPL", "buy", 5, 100.0)
    with pytest.raises(TradeError):
        b.execute("AAPL", "sell", 10, 100.0)


def test_persistence_round_trip():
    b = _broker()
    b.execute("MSFT", "buy", 3, 50.0)
    path = b.path
    reloaded = PaperBroker(path=path)
    assert reloaded.positions["MSFT"]["shares"] == 3
    assert reloaded.cash == b.cash
    os.remove(path)


@pytest.mark.asyncio
async def test_snapshot_values_at_cost_when_no_quote(monkeypatch):
    import app.paper as paper

    async def fake_quotes(symbols):
        return [{"symbol": s, "price": None} for s in symbols]  # simulate no price

    monkeypatch.setattr(paper, "get_quotes", fake_quotes)
    b = _broker()
    b.execute("AAPL", "buy", 10, 100.0)
    snap = await b.snapshot()
    assert snap["equity"] == pytest.approx(STARTING_CASH)  # cost basis fallback
    assert snap["holdings"][0]["ticker"] == "AAPL"
