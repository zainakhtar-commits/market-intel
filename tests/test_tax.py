"""Tests the 2026 tax estimator and the statement-text parser."""
from app.tax import estimate, federal_income_tax, STD_DEDUCTION_2026
from app.finance import parse_statement_text


def test_standard_deductions_2026():
    assert STD_DEDUCTION_2026["single"] == 16_100
    assert STD_DEDUCTION_2026["married"] == 32_200
    assert STD_DEDUCTION_2026["hoh"] == 24_150


def test_low_income_in_10pct_bracket():
    # $10,000 taxable, single: entirely in the 10% bracket
    tax, _, marginal = federal_income_tax(10_000, "single")
    assert tax == 1_000.0
    assert marginal == 0.10


def test_bracket_math_50k_taxable_single():
    # 10% on first 12,400 = 1,240; 12% on (50,000-12,400)=37,600 -> 4,512; total 5,752
    tax, _, marginal = federal_income_tax(50_000, "single")
    assert tax == round(1_240 + 4_512, 2)
    assert marginal == 0.12


def test_estimate_applies_standard_deduction():
    e = estimate(75_000, "single", include_fica=False)
    # taxable = 75,000 - 16,100 = 58,900
    assert e["taxable_income"] == 58_900
    assert e["deduction_is_standard"] is True
    assert e["federal_tax"] > 0
    assert 0 < e["effective_rate"] < 25


def test_estimate_includes_fica():
    e = estimate(75_000, "single", include_fica=True)
    assert e["fica"] > 0
    assert e["total_tax"] == round(e["federal_tax"] + e["fica"], 2)
    assert e["take_home"] == round(e["gross_income"] - e["total_tax"], 2)


def test_married_brackets_differ_from_single():
    s = estimate(120_000, "single", include_fica=False)["federal_tax"]
    m = estimate(120_000, "married", include_fica=False)["federal_tax"]
    assert m < s  # married filing jointly pays less at the same income


def test_zero_income():
    e = estimate(0, "single")
    assert e["total_tax"] == 0
    assert e["effective_rate"] == 0


def test_statement_text_parser():
    text = """
    Account Statement
    06/02 WHOLE FOODS MARKET 86.40
    06/03 NETFLIX.COM 15.99
    06/01 PAYROLL DEPOSIT 3,200.00
    Opening balance 1000.00
    """
    rows = parse_statement_text(text)
    descs = {r["description"] for r in rows}
    assert any("WHOLE FOODS" in d for d in descs)
    payroll = [r for r in rows if "PAYROLL" in r["description"]]
    assert payroll and payroll[0]["amount"] > 0          # deposit -> inflow (positive)
    wf = [r for r in rows if "WHOLE FOODS" in r["description"]]
    assert wf and wf[0]["amount"] < 0                    # purchase -> outflow (negative)
