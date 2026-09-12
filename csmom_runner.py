"""Cross-sectional momentum runner — live/paper trading via Alpaca.

Ranks a universe of liquid large-cap stocks by trailing momentum and holds the
top `top_k`, rebalanced monthly. This is the portfolio-level counterpart to the
single-symbol `bot.py`; it manages the whole account as one momentum portfolio.

Execution model
---------------
- Every day (while the market is open) it fetches daily bars for the universe
  and computes each stock's trailing momentum score (return over `lookback`
  days, skipping the most recent `skip` days).
- On the first trading day of a new month it rebalances: sells any holding that
  dropped out of the top `top_k`, and buys the new top `top_k` (equal weight).
- Trades are placed as notional market orders on Alpaca (paper by default).

Usage
-----
    python csmom_runner.py --dry-run     # show what would be traded, no orders
    python csmom_runner.py              # live paper trading loop
    python csmom_runner.py --top-k 20 --lookback 126
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from csmom import (STOCK_UNIVERSE, LEVERAGED_UNIVERSE, momentum_scores,
                   composite_scores)
from price_feed import _retry_call

DEFAULT_TOP_K = 20
DEFAULT_LOOKBACK = 126
DEFAULT_SKIP = 21
DEFAULT_REBALANCE_DAYS = 30

# Leveraged-momentum defaults (backtested: lookback=21, top_k=2 -> +38% CAGR).
LEVERAGED_TOP_K = 2
LEVERAGED_LOOKBACK = 21

# Composite (range + momentum) defaults: top_k=3, DAILY rebalance.
COMPOSITE_TOP_K = 3
COMPOSITE_LOOKBACK = 21
COMPOSITE_REBALANCE_DAYS = 1

# Daily report is sent once per day at this UTC hour (after US close).
REPORT_HOUR = 21
STATE_FILE = "csmom_state.json"
DASHBOARD_STATE = "csmom_dashboard.json"
LOGBOOK = "logs/csmom_logbook.csv"


def load_env() -> tuple[str, str]:
    from dotenv import load_dotenv
    load_dotenv()
    return os.getenv("ALPACA_API_KEY", ""), os.getenv("ALPACA_API_SECRET", "")


def fetch_universe(symbols: list[str], period: str = "2y") -> dict:
    """Return {'close', 'high', 'low'} DataFrames aligned by date."""
    import yfinance as yf
    df = yf.download(symbols, period=period, interval="1d",
                     auto_adjust=True, progress=False, group_by="column")
    if isinstance(df.columns, pd.MultiIndex):
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
    else:
        close = df
        high = df
        low = df
    return {"close": close.dropna(how="all"), "high": high, "low": low}


def current_rankings(data: dict, lookback: int, skip: int, top_k: int,
                     composite: bool = False) -> list[str]:
    """Return the top `top_k` symbols by score (most recent bar).

    `composite=True` uses the range+momentum blend; otherwise pure momentum.
    """
    if composite:
        scores = composite_scores(data["close"], data["high"], data["low"],
                                  lookback=lookback).iloc[-1].dropna()
    else:
        scores = momentum_scores(data["close"], lookback, skip).iloc[-1].dropna()
    ranked = scores.sort_values(ascending=False)
    return list(ranked.index[:top_k])


class CsmomRunner:
    def __init__(self, top_k: int = DEFAULT_TOP_K, lookback: int = DEFAULT_LOOKBACK,
                 skip: int = DEFAULT_SKIP, paper: bool = True, dry_run: bool = False,
                 symbols: list[str] | None = None, composite: bool = False,
                 rebalance_days: int = DEFAULT_REBALANCE_DAYS):
        self.top_k = top_k
        self.lookback = lookback
        self.skip = skip
        self.dry_run = dry_run
        self.composite = composite
        self.rebalance_days = rebalance_days
        self.symbols = symbols if symbols is not None else STOCK_UNIVERSE
        self.state_path = Path(STATE_FILE)
        self.state = self._load_state()

        api_key, api_secret = load_env()
        if not dry_run:
            from alpaca.trading.client import TradingClient
            self.client = TradingClient(api_key, api_secret, paper=paper)
        else:
            self.client = None

    # --- state ---
    def _load_state(self) -> dict:
        import json
        if self.state_path.exists():
            try:
                s = json.loads(self.state_path.read_text(encoding="utf-8"))
                s.setdefault("last_rebalance_date", None)
                return s
            except (json.JSONDecodeError, OSError):
                pass
        return {"last_rebalance_date": None, "positions": {}}

    def _save_state(self) -> None:
        import json
        self.state_path.write_text(json.dumps(self.state, indent=2),
                                   encoding="utf-8")

    def _write_dashboard_state(self, market_open: bool) -> None:
        """Write a dashboard-readable snapshot (equity, positions, P&L)."""
        import json
        state = {
            "name": ("RANGE+MOMENTUM" if self.composite
                     else ("LEVERAGED MOMENTUM" if self.symbols == LEVERAGED_UNIVERSE
                           else "STOCK MOMENTUM")),
            "strategy": {
                "name": ("composite_range_momentum" if self.composite
                         else ("leveraged_momentum" if self.symbols == LEVERAGED_UNIVERSE
                               else "stock_momentum")),
                "lookback": self.lookback,
                "top_k": self.top_k,
                "skip": self.skip,
                "rebalance_days": self.rebalance_days,
            },
            "symbols": self.symbols,
            "market_open": market_open,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        if self.client is not None:
            try:
                acct = _retry_call(self.client.get_account)
                state["equity"] = float(acct.equity)
                state["balance"] = float(acct.cash)
            except Exception:
                pass
            try:
                positions = {}
                prices = {}
                for p in _retry_call(self.client.get_all_positions):
                    qty = float(p.qty)
                    entry = float(p.avg_entry_price)
                    mv = float(p.market_value or 0.0)
                    upnl = float(p.unrealized_pl or 0.0)
                    cur = float(p.current_price or entry)
                    positions[p.symbol] = {
                        "base_amount": qty,
                        "entry_price": entry,
                        "market_value": mv,
                        "unrealized_pnl": upnl,
                        "stop_price": 0.0,
                        "take_price": 0.0,
                    }
                    prices[p.symbol] = cur
                state["positions"] = positions
                state["prices"] = prices
            except Exception:
                pass
        # Rolling equity history (last 500 snapshots). Persist across cloud
        # runs by reading the previously committed dashboard JSON as the base.
        hist = []
        try:
            prev = json.loads(Path(DASHBOARD_STATE).read_text(encoding="utf-8"))
            hist = prev.get("equity_history", [])
        except (json.JSONDecodeError, OSError):
            pass
        if state.get("equity") is not None:
            new_pt = {"ts": state["last_updated"], "equity": state["equity"]}
            if not hist or hist[-1].get("ts") != new_pt["ts"]:
                hist.append(new_pt)
            hist = hist[-500:]
        self.state["equity_history"] = hist
        state["equity_history"] = hist
        Path(DASHBOARD_STATE).write_text(json.dumps(state, indent=2),
                                         encoding="utf-8")

    # --- Alpaca helpers ---
    def _positions(self) -> dict[str, float]:
        """Return {symbol: market_value} for current open positions."""
        if self.client is None:
            return {}
        out = {}
        for p in _retry_call(self.client.get_all_positions):
            out[p.symbol] = float(p.market_value or 0.0)
        return out

    def _equity(self) -> float:
        if self.client is None:
            return 100000.0
        return float(_retry_call(self.client.get_account).equity)

    def _market_open(self) -> bool:
        if self.client is None:
            return True
        try:
            return bool(_retry_call(self.client.get_clock).is_open)
        except Exception:
            return True

    def _log(self, msg: str) -> None:
        line = f"{datetime.now(timezone.utc).isoformat()} | {msg}"
        print(line, flush=True)
        Path("logs").mkdir(exist_ok=True)
        with open("logs/csmom_runner.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _append_logbook(self, row: list) -> None:
        p = Path(LOGBOOK)
        p.parent.mkdir(parents=True, exist_ok=True)
        new = not p.exists()
        with open(p, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["ts", "action", "symbol", "notional", "reason"])
            w.writerow(row)

    def _maybe_send_report(self, now: datetime) -> None:
        """Send the daily report once per day (after REPORT_HOUR UTC)."""
        today = now.date().isoformat()
        if self.state.get("last_report_date") == today:
            return
        if now.hour < REPORT_HOUR:
            return
        try:
            from report import send_report
            send_report()
            self.state["last_report_date"] = today
            self._save_state()
            self._log("daily report sent")
        except Exception as e:
            self._log(f"report error: {e}")

    # --- rebalance ---
    def rebalance(self, data: dict) -> None:
        targets = current_rankings(data, self.lookback, self.skip, self.top_k,
                                   composite=self.composite)
        current = self._positions()
        equity = self._equity()
        per_position = equity / self.top_k

        to_sell = [s for s in current if s not in targets]
        to_buy = [s for s in targets if s not in current]

        self._log(f"rebalance: equity=${equity:,.0f} top_k={self.top_k} "
                  f"per_position=${per_position:,.0f}")
        self._log(f"  targets ({len(targets)}): {', '.join(targets)}")
        self._log(f"  sell ({len(to_sell)}): {', '.join(to_sell) or '-'}")
        self._log(f"  buy  ({len(to_buy)}): {', '.join(to_buy) or '-'}")

        if self.dry_run:
            for s in to_sell:
                self._append_logbook([datetime.now(timezone.utc).isoformat(),
                                      "SELL (dry)", s, current[s], "dropped out of top"])
            for s in to_buy:
                self._append_logbook([datetime.now(timezone.utc).isoformat(),
                                      "BUY (dry)", s, round(per_position, 2), "entered top"])
            return

        # Sell first (frees buying power), then buy.
        for s in to_sell:
            try:
                _retry_call(self.client.close_position, s)
                self._log(f"  SELL {s}")
                self._append_logbook([datetime.now(timezone.utc).isoformat(),
                                      "SELL", s, round(current[s], 2), "dropped out of top"])
            except Exception as e:
                self._log(f"  SELL {s} FAILED: {e}")

        for s in to_buy:
            try:
                from alpaca.trading.requests import MarketOrderRequest
                from alpaca.trading.enums import OrderSide, TimeInForce
                req = MarketOrderRequest(
                    symbol=s, notional=round(per_position, 2),
                    side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
                )
                _retry_call(self.client.submit_order, req)
                self._log(f"  BUY {s} ${per_position:,.2f}")
                self._append_logbook([datetime.now(timezone.utc).isoformat(),
                                      "BUY", s, round(per_position, 2), "entered top"])
            except Exception as e:
                self._log(f"  BUY {s} FAILED: {e}")

    def tick(self) -> None:
        """Run one iteration: check rebalance, update dashboard, maybe report.

        Idempotent and safe to call repeatedly (e.g. from a scheduler).
        """
        now = datetime.now(timezone.utc)
        market_open = self._market_open()
        last = self.state.get("last_rebalance_date")
        due = last is None
        if not due and last:
            try:
                last_dt = datetime.fromisoformat(last)
                due = (now - last_dt).days >= self.rebalance_days
            except ValueError:
                due = True

        if market_open and due:
            self._log(f"rebalance due (last={last}, every={self.rebalance_days}d)")
            data = fetch_universe(self.symbols)
            self.rebalance(data)
            self.state["last_rebalance_date"] = now.date().isoformat()
            self._save_state()
        else:
            self._log(f"no rebalance (market_open={market_open}, "
                      f"due={due}, last={last})")

        self._write_dashboard_state(market_open)
        self._maybe_send_report(now)

    def run(self, interval_seconds: int = 3600) -> None:
        self._log(f"CSMOM runner started | top_k={self.top_k} "
                  f"lookback={self.lookback} skip={self.skip} "
                  f"composite={self.composite} rebalance_days={self.rebalance_days} "
                  f"dry_run={self.dry_run} universe={len(self.symbols)}")
        while True:
            try:
                self.tick()
            except Exception as e:
                self._log(f"loop error: {e}")
            time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="CSMOM runner")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK)
    parser.add_argument("--skip", type=int, default=DEFAULT_SKIP)
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would be traded without placing orders")
    parser.add_argument("--once", action="store_true",
                        help="run a single rebalance check and exit")
    parser.add_argument("--readonly", action="store_true",
                        help="only refresh the dashboard snapshot (no trading, no report)")
    parser.add_argument("--leveraged", action="store_true",
                        help="use the 3x leveraged ETF universe (momentum rotation)")
    parser.add_argument("--composite", action="store_true",
                        help="use the range+momentum composite signal (weekly rebalance)")
    parser.add_argument("--rebalance-days", type=int, default=None,
                        help="rebalance every N calendar days (default: 30, or 7 for composite)")
    args = parser.parse_args()

    symbols = LEVERAGED_UNIVERSE if args.leveraged else STOCK_UNIVERSE
    if args.composite:
        top_k = COMPOSITE_TOP_K if args.top_k == DEFAULT_TOP_K else args.top_k
        lookback = COMPOSITE_LOOKBACK if args.lookback == DEFAULT_LOOKBACK else args.lookback
        rebalance_days = args.rebalance_days or COMPOSITE_REBALANCE_DAYS
    elif args.leveraged:
        top_k = LEVERAGED_TOP_K if args.top_k == DEFAULT_TOP_K else args.top_k
        lookback = LEVERAGED_LOOKBACK if args.lookback == DEFAULT_LOOKBACK else args.lookback
        rebalance_days = args.rebalance_days or DEFAULT_REBALANCE_DAYS
    else:
        top_k = args.top_k
        lookback = args.lookback
        rebalance_days = args.rebalance_days or DEFAULT_REBALANCE_DAYS

    runner = CsmomRunner(top_k=top_k, lookback=lookback, skip=args.skip,
                         dry_run=args.dry_run, symbols=symbols,
                         composite=args.composite, rebalance_days=rebalance_days)

    if args.once:
        runner.tick()
        return

    if args.readonly:
        runner._write_dashboard_state(runner._market_open())
        return

    if args.dry_run:
        data = fetch_universe(runner.symbols)
        runner.rebalance(data)
        return

    runner.run()


if __name__ == "__main__":
    main()
