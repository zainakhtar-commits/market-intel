"""Signal — a transparent, rules-based rating (Strong Buy ... Strong Sell).

This is NOT investment advice and NOT an analyst recommendation. It is a
mechanical label computed only from two visible factors — 3-month price
momentum and volatility — so the user can see exactly why a name was rated the
way it was and decide for themselves. The thresholds are intentionally simple
and fully disclosed.
"""
from __future__ import annotations

LABELS = ["Strong Sell", "Sell", "Hold", "Buy", "Strong Buy"]


def rate(return_3m: float | None, volatility: float | None = None,
         risk_label: str | None = None) -> dict:
    """Map 3-month momentum (tempered by volatility) to a signal label."""
    r = return_3m or 0.0

    if r >= 20:
        label = "Strong Buy"
    elif r >= 5:
        label = "Buy"
    elif r > -5:
        label = "Hold"
    elif r > -20:
        label = "Sell"
    else:
        label = "Strong Sell"

    # Very high volatility lowers conviction: pull a "Strong" rating one notch in.
    high_vol = (risk_label == "High") or ((volatility or 0) >= 45)
    if high_vol and label == "Strong Buy":
        label = "Buy"
    elif high_vol and label == "Strong Sell":
        label = "Sell"

    vol_txt = (risk_label.lower() if risk_label else None) or (
        "high" if (volatility or 0) >= 45 else "moderate" if (volatility or 0) >= 25 else "low")
    return {
        "label": label,
        "reason": f"3-month return {r:+.1f}% with {vol_txt} volatility"
                  + (f" ({volatility}%)" if volatility is not None else ""),
        "basis": "momentum + volatility only",
    }
