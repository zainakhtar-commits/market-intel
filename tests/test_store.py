from app.schema import Event
from app.store import EventStore


def _ev(id, ticker="AAPL", materiality=0.5, source="edgar"):
    return Event(id=id, source=source, type="filing", title="t",
                 tickers=[ticker], materiality=materiality)


def test_dedupe():
    s = EventStore()
    assert s.add(_ev("a")) is True
    assert s.add(_ev("a")) is False
    assert len(s) == 1


def test_filter_by_materiality_and_ticker():
    s = EventStore()
    s.add(_ev("a", ticker="AAPL", materiality=0.9))
    s.add(_ev("b", ticker="MSFT", materiality=0.2))
    high = s.query(min_materiality=0.5)
    assert [e.id for e in high] == ["a"]
    msft = s.query(ticker="msft")
    assert [e.id for e in msft] == ["b"]


def test_newest_first():
    s = EventStore()
    s.add(_ev("a"))
    s.add(_ev("b"))
    assert [e.id for e in s.query()] == ["b", "a"]
