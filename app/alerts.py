"""Price alerts and conditional simulated orders — user-defined rules.

The USER sets a trigger ("when AAPL goes at/below $200"), optionally with an
action ("auto-buy 10 shares" in the paper account). A background loop checks
live prices and fires matching rules. This is automation of the user's own
rule — it does NOT recommend prices or actions, and any order it places is a
simulated paper trade, never a real one.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

VALID_DIR = {"above", "below"}
VALID_ACTION = {"notify", "buy", "sell"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AlertStore:
    def __init__(self, path: str):
        self.path = path
        self.alerts: list[dict] = []
        self._next_id = 1
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                self.alerts = json.load(f)
            self._next_id = max((a["id"] for a in self.alerts), default=0) + 1
        except Exception as exc:  # noqa: BLE001
            print(f"[alerts] could not load ({exc}); starting empty")

    def _save(self) -> None:
        try:
            with open(self.path, "w") as f:
                json.dump(self.alerts, f, indent=2)
        except Exception as exc:  # noqa: BLE001
            print(f"[alerts] could not save: {exc}")

    def add(self, ticker: str, direction: str, price: float,
            action: str = "notify", shares: float = 0) -> dict:
        ticker = ticker.strip().upper()
        direction = direction.strip().lower()
        action = action.strip().lower()
        if not ticker:
            raise ValueError("Ticker is required.")
        if direction not in VALID_DIR:
            raise ValueError("Direction must be 'above' or 'below'.")
        if action not in VALID_ACTION:
            raise ValueError("Action must be 'notify', 'buy', or 'sell'.")
        if price <= 0:
            raise ValueError("Target price must be greater than 0.")
        if action in {"buy", "sell"} and shares <= 0:
            raise ValueError("Auto-buy/sell needs a share count.")
        alert = {
            "id": self._next_id, "ticker": ticker, "direction": direction,
            "price": float(price), "action": action, "shares": float(shares),
            "status": "active", "created_at": _now(),
            "triggered_at": None, "triggered_price": None, "message": None,
        }
        self._next_id += 1
        self.alerts.append(alert)
        self._save()
        return alert

    def remove(self, alert_id: int) -> bool:
        before = len(self.alerts)
        self.alerts = [a for a in self.alerts if a["id"] != alert_id]
        if len(self.alerts) != before:
            self._save()
            return True
        return False

    def clear_triggered(self) -> None:
        self.alerts = [a for a in self.alerts if a["status"] == "active"]
        self._save()

    def active_tickers(self) -> list[str]:
        return sorted({a["ticker"] for a in self.alerts if a["status"] == "active"})

    def check(self, prices: dict[str, float | None], broker=None) -> list[dict]:
        """Compare active alerts to current prices; fire and (optionally) trade."""
        fired: list[dict] = []
        for a in self.alerts:
            if a["status"] != "active":
                continue
            p = prices.get(a["ticker"])
            if p is None:
                continue
            hit = (a["direction"] == "above" and p >= a["price"]) or \
                  (a["direction"] == "below" and p <= a["price"])
            if not hit:
                continue
            a["status"] = "triggered"
            a["triggered_at"] = _now()
            a["triggered_price"] = round(p, 2)
            msg = f"{a['ticker']} went {a['direction']} ${a['price']:.2f} (now ${p:.2f})"
            if a["action"] in {"buy", "sell"} and a["shares"] > 0 and broker is not None:
                try:
                    broker.execute(a["ticker"], a["action"], a["shares"], p)
                    msg += f" → auto-{a['action']} {a['shares']:g} sh @ ${p:.2f} (simulated)"
                except Exception as exc:  # noqa: BLE001
                    msg += f" → order not filled: {exc}"
            a["message"] = msg
            fired.append(a)
        if fired:
            self._save()
        return fired

    def snapshot(self) -> dict:
        active = [a for a in self.alerts if a["status"] == "active"]
        triggered = [a for a in self.alerts if a["status"] == "triggered"]
        triggered.sort(key=lambda a: a.get("triggered_at") or "", reverse=True)
        return {"active": active, "triggered": triggered}
