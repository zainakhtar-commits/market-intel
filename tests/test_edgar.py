"""Tests the EDGAR parser offline against a captured Atom sample (no network)."""
from app.sources.edgar import SecEdgarSource

SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Latest Filings</title>
  <entry>
    <title>8-K - Apple Inc. (0000320193) (Filer)</title>
    <link rel="alternate" type="text/html" href="https://www.sec.gov/x/apple-8k"/>
    <summary type="html">Form 8-K - Current report</summary>
    <updated>2026-06-12T09:30:00-04:00</updated>
    <id>urn:tag:sec.gov,2008:accession-number=0000320193-26-000077</id>
  </entry>
  <entry>
    <title>4 - SOME INSIDER (0001234567) (Reporting)</title>
    <link rel="alternate" type="text/html" href="https://www.sec.gov/x/insider-4"/>
    <summary type="html">Form 4 - Statement of changes in beneficial ownership</summary>
    <updated>2026-06-12T09:31:00-04:00</updated>
    <id>urn:tag:sec.gov,2008:accession-number=0001234567-26-000001</id>
  </entry>
</feed>"""


def test_parse_feed_extracts_form_company_cik():
    src = SecEdgarSource()
    src._cik_to_ticker = {320193: "AAPL"}  # simulate the loaded ticker map
    events = src._parse_feed(SAMPLE_FEED)
    assert len(events) == 2

    aapl = events[0]
    assert aapl.type == "filing"
    assert aapl.raw["form"] == "8-K"
    assert aapl.raw["company"] == "Apple Inc."
    assert aapl.raw["cik"] == "0000320193"
    assert aapl.tickers == ["AAPL"]  # CIK -> ticker resolution worked
    assert aapl.url == "https://www.sec.gov/x/apple-8k"


def test_parse_feed_dedupes_seen_ids():
    src = SecEdgarSource()
    first = src._parse_feed(SAMPLE_FEED)
    second = src._parse_feed(SAMPLE_FEED)  # same ids -> already seen
    assert len(first) == 2
    assert len(second) == 0


def test_unknown_cik_has_no_ticker():
    src = SecEdgarSource()
    events = src._parse_feed(SAMPLE_FEED)
    insider = [e for e in events if "INSIDER" in e.title][0]
    assert insider.tickers == []
