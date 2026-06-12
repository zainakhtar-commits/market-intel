from app.processing import process
from app.processing import materiality, sentiment
from app.schema import Event


def _ev(**kw) -> Event:
    base = dict(id="t1", source="test", type="news", title="", body="")
    base.update(kw)
    return Event(**base)


def test_sentiment_positive_and_negative():
    assert sentiment.score("revenue rose, strong beat above estimates") > 0
    assert sentiment.score("guidance cut, weak demand, losses widen") < 0
    assert sentiment.score("the company filed a document") == 0.0


def test_materiality_8k_outranks_ownership_form():
    eightk = _ev(type="filing", title="8-K", raw={"form": "8-K"})
    form4 = _ev(type="filing", title="4", raw={"form": "4"})
    assert materiality.score(eightk) > materiality.score(form4)


def test_materiality_bounded():
    ev = _ev(type="news", title="acquisition merger bankruptcy lawsuit guidance earnings")
    assert 0.0 <= materiality.score(ev) <= 1.0


def test_entity_resolution_from_news_text():
    ev = process(_ev(title="Apple beats earnings", body="Apple reported results"))
    assert "AAPL" in ev.tickers


def test_process_fills_all_fields():
    ev = process(_ev(title="Tesla announces acquisition", body="Tesla to acquire a rival"))
    assert ev.summary is not None
    assert ev.materiality > 0
    assert "TSLA" in ev.tickers
