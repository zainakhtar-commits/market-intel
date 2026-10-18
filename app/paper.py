"""Paper-trading broker — a simulator, not a brokerage.

Virtual cash, simulated orders executed at real market prices, full P&L
accounting. No real money and no real order routing — it never connects to a
broker or executes a real trade. This is the "invest and see what the profit
would be" experience, done as a simulation.

State persists to a JSON file so your portfolio survives server restarts.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from app.market import get_quotes

STARTING_CASH = 100_000.0


class TradeError(Exception):
    """Raised when an order can't be filled (funds/shares/price)."""


class PaperBroker:
    def __init__(self, path: str):
        self.path = path
        self.cash: float = STARTING_CASH
        self.positions: dict[str, dict] = {}   # ticker -> {"shares": float, "avg_cost": float}
        self.orders: list[dict] = []           # executed order log
        self.realized_pnl: float = 0.0
        self._load()

    # --- persistence -------------------------------------------------------
    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                data = json.load(f)
            self.cash = data.get("cash", STARTING_CASH)
            self.positions = data.get("positions", {})
            self.orders = data.get("orders", [])
            self.realized_pnl = data.get("realized_pnl", 0.0)
        except Exception as exc:  # noqa: BLE001 - corrupt file shouldn't crash startup
            print(f"[paper] could not load portfolio ({exc}); starting fresh")

    def _save(self) -> None:
        try:
            with open(self.path, "w") as f:
                json.dump({
                    "cash": self.cash,
                    "positions": self.positions,
                    "orders": self.orders,
                    "realized_pnl": self.realized_pnl,
                }, f, indent=2)
        except Exception as exc:  # noqa: BLE001
            print(f"[paper] could not save portfolio: {exc}")

    # --- trading -----------------------------------------------------------
    def execute(self, ticker: str, side: str, shares: float, price: float) -> dict:
        """Fill a market order at `price`. Raises TradeError if it can't fill."""
        ticker = ticker.strip().upper()
        side = side.strip().lower()
        if shares <= 0:
            raise TradeError("Shares must be greater than 0.")
        if price <= 0:
            raise TradeError("No valid market price available for this ticker.")
        if side not in {"buy", "sell"}:
            raise TradeError("Side must be 'buy' or 'sell'.")

        if side == "buy":
            cost = shares * price
            if cost > self.cash + 1e-9:
                raise TradeError(
                    f"Insufficient cash: need ${cost:,.2f}, have ${self.cash:,.2f}."
                )
            self.cash -= cost
            pos = self.positions.get(ticker, {"shares": 0.0, "avg_cost": 0.0})
            new_shares = pos["shares"] + shares
            pos["avg_cost"] = (pos["avg_cost"] * pos["shares"] + cost) / new_shares
            pos["shares"] = new_shares
            self.positions[ticker] = pos
        else:  # sell
            pos = self.positions.get(ticker)
            if not pos or pos["shares"] < shares - 1e-9:
                held = pos["shares"] if pos else 0
                raise TradeError(f"Insufficient shares: trying to sell {shares}, hold {held}.")
            proceeds = shares * price
            self.cash += proceeds
            self.realized_pnl += (price - pos["avg_cost"]) * shares
            pos["shares"] -= shares
            if pos["shares"] <= 1e-9:
                del self.positions[ticker]
            else:
                self.positions[ticker] = pos

        order = {
            "ticker": ticker,
            "side": side,
            "shares": shares,
            "price": round(price, 4),
            "value": round(shares * price, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.orders.append(order)
        self._save()
        return order

    def reset(self) -> None:
        self.cash = STARTING_CASH
        self.positions = {}
        self.orders = []
        self.realized_pnl = 0.0
        self._save()

    # --- valuation ---------------------------------------------------------
    async def snapshot(self) -> dict:
        """Value the portfolio at current market prices."""
        tickers = list(self.positions.keys())
        quotes: dict[str, float | None] = {}
        if tickers:
            for q in await get_quotes(tickers):
                quotes[q["symbol"]] = q.get("price")

        holdings = []
        positions_value = 0.0
        for ticker, pos in self.positions.items():
            price = quotes.get(ticker) or pos["avg_cost"]  # fall back to cost if quote missing
            market_value = price * pos["shares"]
            positions_value += market_value
            unrealized = (price - pos["avg_cost"]) * pos["shares"]
            cost_basis = pos["avg_cost"] * pos["shares"]
            holdings.append({
                "ticker": ticker,
                "shares": round(pos["shares"], 4),
                "avg_cost": round(pos["avg_cost"], 2),
                "price": round(price, 2),
                "market_value": round(market_value, 2),
                "unrealized_pnl": round(unrealized, 2),
                "unrealized_pct": round((unrealized / cost_basis * 100) if cost_basis else 0, 2),
            })

        holdings.sort(key=lambda h: h["market_value"], reverse=True)
        equity = self.cash + positions_value
        return {
            "cash": round(self.cash, 2),
            "positions_value": round(positions_value, 2),
            "equity": round(equity, 2),
            "starting_cash": STARTING_CASH,
            "total_return": round(equity - STARTING_CASH, 2),
            "total_return_pct": round((equity - STARTING_CASH) / STARTING_CASH * 100, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "holdings": holdings,
            "recent_orders": self.orders[-10:][::-1],
        }
