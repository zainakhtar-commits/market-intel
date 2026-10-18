"""Opportunities — surface "potential buy" ideas from transparent screens.

This is an information/analysis tool, NOT investment advice and NOT a
recommendation to buy anything. Each screen is a plain, visible rule applied
to the same growth/risk factors the screener computes, and every idea comes
with a human-readable reason for *why* it matched. The user decides.
"""
from __future__ import annotations

from app.screener import screen
from app.signals import rate

# screen name -> (underlying ranking style, human description)
SCREENS: dict[str, dict[str, str]] = {
    "momentum": {
        "style": "fast_growth",
        "criteria": "Positive 3-month momentum with volatility that isn't extreme.",
    },
    "steady": {
        "style": "steady",
        "criteria": "Low volatility with a flat-to-positive trend.",
    },
    "value_reversal": {
        "style": "balanced",
        "criteria": "Pulled back over the last month but still positive over 3 months.",
    },
}


def _passes(row: dict, name: str) -> bool:
    r1 = row.get("return_1m") or 0.0
    r3 = row.get("return_3m") or 0.0
    risk = row.get("risk_label")
    if name == "momentum":
        return r3 > 5 and risk != "High"
    if name == "steady":
        return risk == "Low" and r3 >= 0
    if name == "value_reversal":
        return r1 < 0 and r3 > 0
    return False


def _reason(row: dict, name: str) -> str:
    r1 = row.get("return_1m")
    r3 = row.get("return_3m")
    vol = row.get("volatility")
    if name == "momentum":
        return f"+{r3}% over 3 months with {str(row.get('risk_label')).lower()} volatility ({vol}%)."
    if name == "steady":
        return f"Low volatility ({vol}%) with a {'positive' if (r3 or 0) >= 0 else 'flat'} 3-month trend."
    if name == "value_reversal":
        return f"Down {r1}% this month but still +{r3}% over 3 months — a possible pullback."
    return "Matches the selected screen."


def build(rows: list[dict], name: str, limit: int = 10) -> list[dict]:
    """Filter ranked rows by the screen and attach reasons (pure, testable)."""
    ideas = []
    for row in rows:
        if _passes(row, name):
            sig = rate(row.get("return_3m"), row.get("volatility"), row.get("risk_label"))
            ideas.append({**row, "reason": _reason(row, name), "signal": sig["label"]})
    return ideas[:limit]


async def find_opportunities(universe: list[str] | None = None,
                             screen_name: str = "momentum",
                             limit: int = 10) -> dict:
    name = screen_name if screen_name in SCREENS else "momentum"
    style = SCREENS[name]["style"]
    rows = await screen(universe=universe, style=style)
    ideas = build(rows, name, limit=limit)
    return {
        "screen": name,
        "criteria": SCREENS[name]["criteria"],
        "available_screens": list(SCREENS.keys()),
        "disclaimer": (
            "Ideas matching a transparent screen — information and analysis only. "
            "NOT investment advice or a recommendation to buy. You decide."
        ),
        "count": len(ideas),
        "ideas": ideas,
    }
