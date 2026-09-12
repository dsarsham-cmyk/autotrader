"""Persistent bot state (JSON).

Saves balance, positions, trade history, and equity history so the bot can
resume after a restart, and so the dashboard can display live status.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


class StateStore:
    def __init__(self, path: str = "state.json"):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.data = {
            "balance": 0.0,
            "equity": 0.0,          # total account equity (for the dashboard)
            "market_open": False,   # whether the market is currently open
            "symbols": [],          # list of symbols the bot is trading
            "prices": {},           # symbol -> latest price
            "signals": {},          # symbol -> current signal (buy/sell/hold)
            "positions": {},        # symbol -> {base_amount, entry_price, ...}
            "trades": [],           # list of trade dicts
            "equity_history": [],   # list of {ts, equity}
            "pnl": {},               # symbol -> cumulative realized P&L ($)
            "pnl_history": {},       # symbol -> list of {ts, pnl} (total P&L over time)
            "started_at": None,
            "last_updated": None,
        }
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass

    def save(self) -> None:
        self.data["last_updated"] = datetime.now(timezone.utc).isoformat()
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, default=str)
            tmp.replace(self.path)

    def record_trade(self, side: str, symbol: str, price: float,
                     base_amount: float, quote_amount: float, fee: float) -> None:
        self.data["trades"].append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "side": side,
            "symbol": symbol,
            "price": price,
            "base_amount": base_amount,
            "quote_amount": quote_amount,
            "fee": fee,
        })
        # Cap history to avoid unbounded growth.
        if len(self.data["trades"]) > 5000:
            self.data["trades"] = self.data["trades"][-5000:]

    def record_equity(self, equity: float) -> None:
        self.data["equity_history"].append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "equity": equity,
        })
        if len(self.data["equity_history"]) > 5000:
            self.data["equity_history"] = self.data["equity_history"][-5000:]

    def set_position(self, symbol: str, base_amount: float, entry_price: float,
                     stop_price: float = 0.0, take_price: float = 0.0,
                     trailing_high: float = 0.0) -> None:
        self.data["positions"][symbol] = {
            "base_amount": base_amount,
            "entry_price": entry_price,
            "stop_price": stop_price,
            "take_price": take_price,
            "trailing_high": trailing_high,
        }

    def get_position(self, symbol: str) -> dict:
        return self.data["positions"].get(symbol, {
            "base_amount": 0.0, "entry_price": 0.0,
            "stop_price": 0.0, "take_price": 0.0, "trailing_high": 0.0,
        })

    def add_realized_pnl(self, symbol: str, amount: float) -> None:
        """Accumulate realized P&L for a symbol (called on each sell)."""
        self.data["pnl"][symbol] = self.data["pnl"].get(symbol, 0.0) + amount

    def record_pnl_history(self, symbol: str, total_pnl: float) -> None:
        """Record a per-symbol total-P&L point (realized + unrealized)."""
        hist = self.data["pnl_history"].setdefault(symbol, [])
        hist.append({"ts": datetime.now(timezone.utc).isoformat(), "pnl": total_pnl})
        if len(hist) > 5000:
            self.data["pnl_history"][symbol] = hist[-5000:]
