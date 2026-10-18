"""Tests the transparent rules-based signal (offline, deterministic)."""
from app.signals import rate


def test_rate_bands():
    assert rate(25, 20, "Medium")["label"] == "Strong Buy"
    assert rate(10, 20, "Medium")["label"] == "Buy"
    assert rate(0, 20, "Low")["label"] == "Hold"
    assert rate(-10, 20, "Medium")["label"] == "Sell"
    assert rate(-30, 20, "Medium")["label"] == "Strong Sell"


def test_high_volatility_tempers_strong_ratings():
    assert rate(30, 60, "High")["label"] == "Buy"       # Strong Buy -> Buy
    assert rate(-30, 60, "High")["label"] == "Sell"     # Strong Sell -> Sell


def test_reason_mentions_momentum():
    r = rate(12.3, 22.0, "Low")
    assert "3-month return +12.3%" in r["reason"]
    assert r["basis"] == "momentum + volatility only"
