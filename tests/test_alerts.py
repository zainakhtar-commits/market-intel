"""Tests the price-alerts engine and conditional simulated orders."""
import os
import tempfile

import pytest

from app.alerts import AlertStore


def _store():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)
    return AlertStore(path=path)


class FakeBroker:
    def __init__(self):
        self.executed = []

    def execute(self, ticker, side, shares, price):
        self.executed.append((ticker, side, shares, price))
        return {}


def test_add_validates():
    s = _store()
    with pytest.raises(ValueError):
        s.add("AAPL", "sideways", 200)            # bad direction
    with pytest.raises(ValueError):
        s.add("AAPL", "below", 0)                 # bad price
    with pytest.raises(ValueError):
        s.add("AAPL", "below", 200, "buy", 0)     # buy needs shares


def test_below_trigger_fires():
    s = _store()
    s.add("AAPL", "below", 200)
    fired = s.check({"AAPL": 195.0})
    assert len(fired) == 1
    assert s.snapshot()["triggered"][0]["ticker"] == "AAPL"


def test_above_not_triggered_when_price_lower():
    s = _store()
    s.add("AAPL", "above", 250)
    fired = s.check({"AAPL": 240.0})
    assert fired == []
    assert len(s.snapshot()["active"]) == 1


def test_auto_buy_executes_paper_order_on_trigger():
    s = _store()
    s.add("AAPL", "below", 200, action="buy", shares=10)
    broker = FakeBroker()
    s.check({"AAPL": 199.0}, broker=broker)
    assert broker.executed == [("AAPL", "buy", 10, 199.0)]


def test_active_tickers_excludes_triggered():
    s = _store()
    s.add("AAPL", "below", 200)
    s.add("MSFT", "above", 400)
    s.check({"AAPL": 199.0})           # AAPL triggers
    assert s.active_tickers() == ["MSFT"]


def test_remove_and_persistence():
    s = _store()
    a = s.add("AAPL", "below", 200)
    path = s.path
    reloaded = AlertStore(path=path)
    assert len(reloaded.snapshot()["active"]) == 1
    assert reloaded.remove(a["id"]) is True
    assert reloaded.snapshot()["active"] == []
    os.remove(path)
