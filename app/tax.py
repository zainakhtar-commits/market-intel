"""Tax estimator — 2026 US federal income tax + FICA (transparent estimate).

Uses the IRS inflation-adjusted 2026 brackets and standard deductions (Rev.
Proc. 2025-32, via the Tax Foundation). This is an ESTIMATE for understanding —
not tax advice, not a tax return. It covers federal income tax + an approximate
FICA line; it does not handle state tax, credits, itemized deductions, or many
special cases.
"""
from __future__ import annotations

# 2026 brackets as (rate, lower_bound). Tax applies progressively above each bound.
BRACKETS_2026: dict[str, list[tuple[float, float]]] = {
    "single": [(0.10, 0), (0.12, 12_400), (0.22, 50_400), (0.24, 105_700),
               (0.32, 201_775), (0.35, 256_225), (0.37, 640_600)],
    "married": [(0.10, 0), (0.12, 24_800), (0.22, 100_800), (0.24, 211_400),
                (0.32, 403_550), (0.35, 512_450), (0.37, 768_700)],
    "hoh": [(0.10, 0), (0.12, 17_700), (0.22, 67_450), (0.24, 105_700),
            (0.32, 201_775), (0.35, 256_200), (0.37, 640_600)],
}
STD_DEDUCTION_2026 = {"single": 16_100, "married": 32_200, "hoh": 24_150}

# FICA 2026 (approximate). Social Security 6.2% up to the wage base; Medicare 1.45%
# on all wages (+0.9% additional Medicare over the threshold).
SS_RATE = 0.062
SS_WAGE_BASE = 184_500          # 2026 estimate; SS portion caps here
MEDICARE_RATE = 0.0145
ADDL_MEDICARE_RATE = 0.009
ADDL_MEDICARE_THRESHOLD = {"single": 200_000, "married": 250_000, "hoh": 200_000}


def _normalize_status(status: str) -> str:
    s = (status or "single").strip().lower()
    if s in {"married", "mfj", "married_joint", "joint"}:
        return "married"
    if s in {"hoh", "head", "head_of_household"}:
        return "hoh"
    return "single"


def federal_income_tax(taxable: float, status: str = "single") -> tuple[float, list[dict], float]:
    """Return (tax, per-bracket breakdown, marginal rate)."""
    status = _normalize_status(status)
    brackets = BRACKETS_2026[status]
    taxable = max(0.0, taxable)
    tax = 0.0
    breakdown: list[dict] = []
    marginal = brackets[0][0]
    for i, (rate, lower) in enumerate(brackets):
        upper = brackets[i + 1][1] if i + 1 < len(brackets) else float("inf")
        if taxable > lower:
            amount_in = min(taxable, upper) - lower
            t = amount_in * rate
            tax += t
            marginal = rate
            breakdown.append({"rate": rate, "from": lower,
                              "to": (None if upper == float("inf") else upper),
                              "taxed": round(amount_in, 2), "tax": round(t, 2)})
        else:
            break
    return round(tax, 2), breakdown, marginal


def fica(gross: float, status: str = "single") -> float:
    status = _normalize_status(status)
    ss = min(gross, SS_WAGE_BASE) * SS_RATE
    med = gross * MEDICARE_RATE
    addl = max(0.0, gross - ADDL_MEDICARE_THRESHOLD[status]) * ADDL_MEDICARE_RATE
    return round(ss + med + addl, 2)


def estimate(gross_income: float, status: str = "single",
             deduction: float | None = None, include_fica: bool = True) -> dict:
    status = _normalize_status(status)
    gross_income = max(0.0, gross_income)
    std = STD_DEDUCTION_2026[status]
    ded = std if deduction is None else max(0.0, deduction)
    taxable = max(0.0, gross_income - ded)

    fed, breakdown, marginal = federal_income_tax(taxable, status)
    fica_amt = fica(gross_income, status) if include_fica else 0.0
    total = round(fed + fica_amt, 2)
    take_home = round(gross_income - total, 2)
    eff = round(total / gross_income * 100, 2) if gross_income else 0.0

    return {
        "year": 2026,
        "status": status,
        "gross_income": round(gross_income, 2),
        "deduction": round(ded, 2),
        "deduction_is_standard": deduction is None,
        "taxable_income": round(taxable, 2),
        "federal_tax": fed,
        "fica": fica_amt,
        "total_tax": total,
        "take_home": take_home,
        "effective_rate": eff,
        "marginal_rate": round(marginal * 100, 1),
        "breakdown": breakdown,
        "disclaimer": "Estimate only — 2026 federal income tax + approximate FICA. "
                      "Excludes state tax, credits, and itemized deductions. Not tax advice.",
    }
