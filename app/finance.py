"""Personal-finance helper — fully local, no bank connections.

The user manages accounts by nickname (no real account numbers), uploads their
own statement CSV, and the app categorizes spending, flags charges worth
reviewing, and shows where the money goes. Everything is stored locally in a
JSON file on the user's machine — nothing is sent anywhere.

It does NOT connect to banks with credentials, and its spending observations are
information/analysis, not licensed financial advice.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import statistics
from datetime import datetime

# Account types and whether they count as assets (+) or liabilities (-).
LIABILITY_TYPES = {"credit", "loan"}

CATEGORY_RULES: dict[str, list[str]] = {
    "Income": ["payroll", "salary", "direct dep", "direct deposit", "refund", "interest", "dividend", "reimburse"],
    "Groceries": ["grocery", "supermarket", "whole foods", "trader joe", "safeway", "kroger", "aldi", "costco", "walmart", "wegmans", "publix"],
    "Dining": ["restaurant", "cafe", "coffee", "starbucks", "mcdonald", "chipotle", "doordash", "uber eats", "grubhub", "pizza", "taco", "diner", "bar "],
    "Transport": ["uber", "lyft", "shell", "chevron", "exxon", "bp ", "gas station", "transit", "parking", "metro", "delta air", "united air", "amtrak"],
    "Subscriptions": ["netflix", "spotify", "hulu", "disney+", "youtube premium", "icloud", "adobe", "patreon", "hbo", "membership", "gym", "fitness", "audible"],
    "Shopping": ["amazon", "ebay", "best buy", "apple store", "nike", "target", "etsy", "store"],
    "Utilities": ["electric", "water util", "comcast", "xfinity", "at&t", "verizon", "t-mobile", "internet", "utility", "pg&e"],
    "Housing": ["rent", "mortgage", "landlord", "apartment", "hoa"],
    "Health": ["pharmacy", "cvs", "walgreens", "doctor", "dental", "clinic", "hospital", "medical"],
    "Entertainment": ["cinema", "movie", "theater", "steam", "playstation", "xbox", "concert", "ticketmaster", "spotify"],
}


def _parsenum(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace("$", "").replace(",", "")
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        n = float(s)
        return -n if neg else n
    except ValueError:
        return None


def categorize(description: str, amount: float) -> str:
    d = (description or "").lower()
    if amount > 0:
        for kw in CATEGORY_RULES["Income"]:
            if kw in d:
                return "Income"
        return "Income"
    for cat, kws in CATEGORY_RULES.items():
        if cat == "Income":
            continue
        if any(kw in d for kw in kws):
            return cat
    return "Other"


def parse_csv(text: str) -> list[dict]:
    """Parse a bank/card CSV with flexible column names. Negative = spending."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    fmap = {f.lower().strip(): f for f in reader.fieldnames if f}

    def find(*cands):
        for c in cands:
            for low, orig in fmap.items():
                if c in low:
                    return orig
        return None

    date_f = find("date", "posted", "transaction date")
    desc_f = find("description", "payee", "name", "memo", "details", "merchant")
    amt_f = find("amount", "transaction amount")
    debit_f = find("debit", "withdrawal", "outflow")
    credit_f = find("credit", "deposit", "inflow")

    out: list[dict] = []
    for row in reader:
        desc = (row.get(desc_f) or "").strip() if desc_f else ""
        date = (row.get(date_f) or "").strip() if date_f else ""
        amount = None
        if amt_f and (row.get(amt_f) or "").strip():
            amount = _parsenum(row.get(amt_f))
        elif debit_f or credit_f:
            deb = _parsenum(row.get(debit_f)) if debit_f else None
            cre = _parsenum(row.get(credit_f)) if credit_f else None
            if deb:
                amount = -abs(deb)
            elif cre:
                amount = abs(cre)
        if amount is None or not desc:
            continue
        out.append({"date": date, "description": desc, "amount": round(amount, 2)})
    return out


_DATE_RE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{4}-\d{2}-\d{2}|[A-Z][a-z]{2}\.?\s+\d{1,2})\b")
_AMT_RE = re.compile(r"\(?-?\$?\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})\)?-?")
_INFLOW_HINTS = ("payment", "deposit", "credit", "refund", "reversal", "interest", "payroll", "transfer in")


def parse_statement_text(text: str) -> list[dict]:
    """Best-effort transaction extraction from free-form statement text (e.g. PDF).

    PDF layouts vary a lot, so this is heuristic: a line needs a date and a
    money amount; the text between becomes the description. Sign is inferred
    (parentheses / trailing minus = outflow; deposit/credit keywords = inflow).
    """
    out: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if len(line) < 8:
            continue
        dm = _DATE_RE.search(line)
        amts = _AMT_RE.findall(line)
        if not dm or not amts:
            continue
        amt_str = amts[-1].strip()  # last money token on the line is usually the amount
        neg = amt_str.startswith("(") or amt_str.endswith("-") or amt_str.lstrip().startswith("-")
        val = _parsenum(amt_str.strip("()-").replace("$", "").strip())
        if val is None or val == 0:
            continue
        val = abs(val)
        low = line.lower()
        inflow = any(h in low for h in _INFLOW_HINTS)
        amount = val if inflow else -val
        if neg and not inflow:
            amount = -val
        # description = line minus the date and the trailing amount
        desc = line[dm.end():]
        desc = desc.replace(amts[-1], "").strip(" \t-—|")
        desc = re.sub(r"\s{2,}", " ", desc) or "Transaction"
        out.append({"date": dm.group(1), "description": desc[:80], "amount": round(amount, 2)})
    return out


def extract_pdf_text(data: bytes) -> str:
    """Extract text from a PDF using pdfplumber (lazy import; optional dependency)."""
    import io as _io
    try:
        import pdfplumber  # type: ignore
    except ImportError as exc:  # noqa: BLE001
        raise RuntimeError("PDF support needs the 'pdfplumber' package (pip install pdfplumber).") from exc
    text_parts: list[str] = []
    with pdfplumber.open(_io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts)


def detect_recurring(spend: list[dict]) -> list[dict]:
    """Merchants charging a similar amount 2+ times look like subscriptions."""
    groups: dict[str, list[dict]] = {}
    for t in spend:
        key = re.sub(r"[^a-z]", "", t["description"].lower())[:12]
        groups.setdefault(key, []).append(t)
    recurring = []
    for key, g in groups.items():
        if len(g) >= 2:
            amts = [abs(t["amount"]) for t in g]
            if max(amts) - min(amts) <= max(2.0, statistics.mean(amts) * 0.15):
                recurring.append({"merchant": g[0]["description"], "count": len(g),
                                  "amount": round(statistics.mean(amts), 2)})
    recurring.sort(key=lambda r: -r["amount"] * r["count"])
    return recurring


def find_anomalies(txns: list[dict]) -> list[dict]:
    spend = [t for t in txns if t["amount"] < 0]
    flags: list[dict] = []
    amts = [abs(t["amount"]) for t in spend]
    if len(amts) >= 3:
        # Median is robust: a single huge charge doesn't inflate the baseline and hide itself.
        med = statistics.median(amts)
        thresh = max(med * 8, 150)
        for t in spend:
            if abs(t["amount"]) > thresh:
                flags.append({**t, "reason": "Unusually large charge vs your typical spending"})
    # duplicates: same amount + similar merchant
    seen: dict[tuple, list[dict]] = {}
    for t in spend:
        key = (round(t["amount"], 2), re.sub(r"[^a-z]", "", t["description"].lower())[:14])
        seen.setdefault(key, []).append(t)
    for key, g in seen.items():
        if len(g) >= 2:
            flags.append({**g[-1], "reason": f"Possible duplicate charge ({len(g)}x identical)"})
    return flags


def build_insights(txns: list[dict]) -> dict:
    spend = [t for t in txns if t["amount"] < 0]
    income = [t for t in txns if t["amount"] > 0]
    by_cat: dict[str, float] = {}
    for t in spend:
        c = categorize(t["description"], t["amount"])
        by_cat[c] = by_cat.get(c, 0) + abs(t["amount"])
    cats = sorted(by_cat.items(), key=lambda x: -x[1])
    total_spend = round(sum(abs(t["amount"]) for t in spend), 2)
    total_income = round(sum(t["amount"] for t in income), 2)
    recurring = detect_recurring(spend)

    notes: list[str] = []
    subs = by_cat.get("Subscriptions", 0)
    if subs > 0:
        notes.append(f"You spent ${subs:,.0f} on subscriptions/memberships — cancel any you don't use.")
    dining = by_cat.get("Dining", 0)
    if total_spend and dining > total_spend * 0.15:
        notes.append(f"Dining is ${dining:,.0f} ({dining / total_spend * 100:.0f}% of spending) — a common place to cut back.")
    if recurring:
        rec_total = sum(r["amount"] * r["count"] for r in recurring)
        notes.append(f"Found {len(recurring)} recurring charges totaling ~${rec_total:,.0f} — review them.")
    if total_income and total_spend:
        net = total_income - total_spend
        if net > 0:
            notes.append(f"You netted +${net:,.0f} (income minus spending) over this data — consider saving/investing the surplus.")
        else:
            notes.append(f"Spending exceeded income by ${-net:,.0f} over this data — worth tightening the top categories.")
    if not notes:
        notes.append("Upload a statement to see personalized spending observations.")

    return {
        "total_spend": total_spend,
        "total_income": total_income,
        "net": round(total_income - total_spend, 2),
        "by_category": [{"category": c, "amount": round(v, 2)} for c, v in cats],
        "recurring": recurring,
        "notes": notes,
        "transaction_count": len(txns),
    }


def sample_transactions() -> list[dict]:
    """Realistic sample so the user can see it work without uploading anything."""
    rows = [
        ("2026-06-01", "PAYROLL DIRECT DEPOSIT EMPLOYER", 3200.00),
        ("2026-06-02", "WHOLE FOODS MARKET", -86.40),
        ("2026-06-02", "STARBUCKS STORE 123", -6.75),
        ("2026-06-03", "NETFLIX.COM", -15.99),
        ("2026-06-03", "SPOTIFY USA", -10.99),
        ("2026-06-04", "UBER TRIP", -22.30),
        ("2026-06-05", "AMAZON MARKETPLACE", -54.20),
        ("2026-06-06", "SHELL GAS STATION", -48.10),
        ("2026-06-07", "CHIPOTLE ONLINE", -13.45),
        ("2026-06-08", "RENT PAYMENT LANDLORD", -1650.00),
        ("2026-06-09", "DOORDASH ORDER", -31.80),
        ("2026-06-10", "PLANET FITNESS MEMBERSHIP", -24.99),
        ("2026-06-11", "AMAZON MARKETPLACE", -54.20),  # duplicate-ish
        ("2026-06-12", "BEST BUY ELECTRONICS", -1299.00),  # large
        ("2026-06-13", "STARBUCKS STORE 456", -5.95),
        ("2026-06-14", "COMCAST XFINITY INTERNET", -79.99),
        ("2026-06-15", "TRADER JOES", -42.18),
        ("2026-06-16", "NETFLIX.COM", -15.99),  # recurring next cycle
    ]
    return [{"date": d, "description": desc, "amount": amt} for d, desc, amt in rows]


class FinanceStore:
    def __init__(self, path: str):
        self.path = path
        self.accounts: list[dict] = []
        self.transactions: list[dict] = []
        self._acc_id = 1
        self._txn_id = 1
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                d = json.load(f)
            self.accounts = d.get("accounts", [])
            self.transactions = d.get("transactions", [])
            self._acc_id = max((a["id"] for a in self.accounts), default=0) + 1
            self._txn_id = max((t["id"] for t in self.transactions), default=0) + 1
        except Exception as exc:  # noqa: BLE001
            print(f"[finance] could not load ({exc})")

    def _save(self) -> None:
        try:
            with open(self.path, "w") as f:
                json.dump({"accounts": self.accounts, "transactions": self.transactions}, f, indent=2)
        except Exception as exc:  # noqa: BLE001
            print(f"[finance] could not save: {exc}")

    # accounts
    def add_account(self, name: str, type_: str, balance: float) -> dict:
        a = {"id": self._acc_id, "name": name.strip(), "type": type_.strip().lower(), "balance": float(balance)}
        self._acc_id += 1
        self.accounts.append(a)
        self._save()
        return a

    def remove_account(self, acc_id: int) -> bool:
        before = len(self.accounts)
        self.accounts = [a for a in self.accounts if a["id"] != acc_id]
        if len(self.accounts) != before:
            self._save()
            return True
        return False

    def net_worth(self) -> float:
        total = 0.0
        for a in self.accounts:
            total += -a["balance"] if a["type"] in LIABILITY_TYPES else a["balance"]
        return round(total, 2)

    # transactions
    def import_rows(self, rows: list[dict]) -> int:
        for r in rows:
            r = {**r, "id": self._txn_id, "category": categorize(r["description"], r["amount"])}
            self._txn_id += 1
            self.transactions.append(r)
        self._save()
        return len(rows)

    def clear_transactions(self) -> None:
        self.transactions = []
        self._save()

    def snapshot(self) -> dict:
        return {
            "accounts": self.accounts,
            "net_worth": self.net_worth(),
            "transaction_count": len(self.transactions),
            "insights": build_insights(self.transactions),
            "anomalies": find_anomalies(self.transactions),
            "recent": sorted(self.transactions, key=lambda t: t.get("date", ""), reverse=True)[:30],
        }
