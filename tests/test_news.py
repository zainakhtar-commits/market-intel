"""Offline tests for the Google News RSS parser and index symbol mapping."""
from app.sources.news import GoogleNewsSource
from app.market import _to_stooq_symbol

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>AAPL stock - Google News</title>
  <item>
    <title>Apple hits record high on strong iPhone demand - Reuters</title>
    <link>https://news.google.com/articles/aaa</link>
    <guid>guid-aaa</guid>
    <pubDate>Fri, 12 Jun 2026 13:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Apple unveils new AI chip - Bloomberg</title>
    <link>https://news.google.com/articles/bbb</link>
    <guid>guid-bbb</guid>
    <pubDate>Fri, 12 Jun 2026 12:00:00 GMT</pubDate>
  </item>
</channel></rss>"""


def test_news_parses_and_tags_ticker():
    src = GoogleNewsSource(tickers=["AAPL"])
    events = src._parse(SAMPLE_RSS, "AAPL")
    assert len(events) == 2
    e = events[0]
    assert e.type == "news"
    assert e.source == "news"
    assert e.tickers == ["AAPL"]
    assert e.title == "Apple hits record high on strong iPhone demand"  # publisher stripped
    assert e.raw["publisher"] == "Reuters"
    assert e.url == "https://news.google.com/articles/aaa"


def test_news_dedupes_seen_guids():
    src = GoogleNewsSource(tickers=["AAPL"])
    first = src._parse(SAMPLE_RSS, "AAPL")
    second = src._parse(SAMPLE_RSS, "AAPL")
    assert len(first) == 2
    assert len(second) == 0


def test_news_same_headline_tracked_per_ticker():
    src = GoogleNewsSource(tickers=["AAPL", "MSFT"])
    a = src._parse(SAMPLE_RSS, "AAPL")
    m = src._parse(SAMPLE_RSS, "MSFT")  # same guids, different ticker key -> not deduped
    assert len(a) == 2 and len(m) == 2
    assert m[0].tickers == ["MSFT"]


def test_index_symbol_mapping():
    assert _to_stooq_symbol("AAPL") == "aapl.us"
    assert _to_stooq_symbol("^SPX") == "^spx"      # index keeps no .us suffix
    assert _to_stooq_symbol("brk.b") == "brk.b"    # already has a dot
