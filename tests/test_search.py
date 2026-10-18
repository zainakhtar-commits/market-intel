"""Tests company search ranking (name + ticker), offline."""
from app.financials import _rank_companies

NAMES = {
    "AAPL": "Apple Inc.",
    "GOOGL": "Alphabet Inc.",
    "GOOG": "Alphabet Inc.",
    "META": "Meta Platforms, Inc.",
    "MSFT": "Microsoft Corporation",
    "YELP": "Yelp Inc.",
    "AMZN": "Amazon.com, Inc.",
}


def test_match_by_company_name():
    # "google" isn't a ticker, but the name search should surface Alphabet
    res = _rank_companies("alphabet", NAMES)
    tickers = [r["ticker"] for r in res]
    assert "GOOGL" in tickers and "GOOG" in tickers


def test_exact_ticker_ranks_first():
    res = _rank_companies("META", NAMES)
    assert res[0]["ticker"] == "META"


def test_prefix_letter_returns_matches():
    # typing "y" should surface Yelp (ticker starts with Y)
    res = _rank_companies("Y", NAMES)
    assert any(r["ticker"] == "YELP" for r in res)


def test_name_contains_match():
    res = _rank_companies("platforms", NAMES)
    assert res[0]["ticker"] == "META"


def test_empty_query_returns_nothing():
    assert _rank_companies("", NAMES) == []


def test_limit_respected():
    res = _rank_companies("inc", NAMES, limit=2)
    assert len(res) <= 2
