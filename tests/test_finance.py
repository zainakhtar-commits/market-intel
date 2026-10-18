"""Tests CSV parsing, categorization, anomalies, insights, accounts."""
import os
import tempfile

from app.finance import (
    parse_csv, categorize, find_anomalies, build_insights,
    detect_recurring, sample_transactions, FinanceStore,
)

CSV_AMOUNT = """Date,Description,Amount
2026-06-01,PAYROLL DEPOSIT,3000.00
2026-06-02,WHOLE FOODS MARKET,-80.00
2026-06-03,NETFLIX.COM,-15.99
"""

CSV_DEBIT_CREDIT = """Posted,Payee,Debit,Credit
06/01,Employer Direct Deposit,,3000.00
06/02,Starbucks,6.50,
06/03,Shell Gas,40.00,
"""


def test_parse_amount_layout():
    rows = parse_csv(CSV_AMOUNT)
    assert len(rows) == 3
    assert rows[0]["amount"] == 3000.0
    assert rows[1]["amount"] == -80.0


def test_parse_debit_credit_layout():
    rows = parse_csv(CSV_DEBIT_CREDIT)
    assert len(rows) == 3
    # debit -> negative (spending), credit -> positive (income)
    assert rows[0]["amount"] == 3000.0
    assert rows[1]["amount"] == -6.5


def test_categorize():
    assert categorize("WHOLE FOODS MARKET", -80) == "Groceries"
    assert categorize("NETFLIX.COM", -15.99) == "Subscriptions"
    assert categorize("PAYROLL DEPOSIT", 3000) == "Income"
    assert categorize("MYSTERY VENDOR XYZ", -12) == "Other"


def test_anomalies_flags_large_and_duplicate():
    txns = [
        {"date": "2026-06-01", "description": "Coffee", "amount": -5},
        {"date": "2026-06-02", "description": "Coffee", "amount": -5},
        {"date": "2026-06-03", "description": "Lunch", "amount": -12},
        {"date": "2026-06-04", "description": "Big TV Store", "amount": -1500},
        {"date": "2026-06-05", "description": "Coffee", "amount": -5},  # duplicate set
    ]
    flags = find_anomalies(txns)
    reasons = " ".join(f["reason"] for f in flags)
    assert "large" in reasons.lower()
    assert "duplicate" in reasons.lower()


def test_recurring_detection():
    spend = [
        {"date": "2026-05-03", "description": "NETFLIX.COM", "amount": -15.99},
        {"date": "2026-06-03", "description": "NETFLIX.COM", "amount": -15.99},
    ]
    rec = detect_recurring(spend)
    assert rec and rec[0]["count"] == 2


def test_insights_structure():
    ins = build_insights(sample_transactions())
    assert ins["total_spend"] > 0
    assert ins["total_income"] > 0
    assert any(c["category"] == "Subscriptions" for c in ins["by_category"])
    assert ins["notes"]


def _store():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)
    return FinanceStore(path=path)


def test_net_worth_treats_liabilities_as_negative():
    s = _store()
    s.add_account("Checking", "checking", 5000)
    s.add_account("Visa", "credit", 1200)   # owed -> subtract
    assert s.net_worth() == 3800.0
    os.remove(s.path)


def test_import_assigns_category_and_persists():
    s = _store()
    n = s.import_rows(parse_csv(CSV_AMOUNT))
    assert n == 3
    reloaded = FinanceStore(path=s.path)
    assert len(reloaded.transactions) == 3
    assert reloaded.transactions[1]["category"] == "Groceries"
    os.remove(s.path)
