"""Pairs trading / statistical arbitrage runner.

Backtests and live-executes a long-short mean-reversion strategy on the log
price ratio of two correlated ETFs (e.g. QQQ vs SPY, EWJ vs EZU).

When one leg becomes expensive relative to the other (spread z-score beyond
`entry_z`), short the expensive leg and long the cheap leg, betting on
convergence. Exit when the spread reverts (|z| < `exit_z`).

Usage:
    python pairs.py --backtest          # backtest the configured pair
    python pairs.py                     # live paper-trade the configured pair
"""
from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import yaml

from strategy import PairsTrading
from broker import AlpacaBroker
from price_feed import StockPriceFeed
from logger import setup_logger
from state import StateStore


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def pair_settings(config: dict) -> dict:
    return config.get("pairs", {})


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

def run_pairs_backtest(candles_a: list, candles_b: list, strategy: PairsTrading,
                       start_equity: float = 100000.0, fee_pct: float = 0.001,
                       leg_pct: float = 0.5) -> dict:
    """Simulate a long-short pairs strategy over two aligned candle series.

    Each leg is allocated `leg_pct` of current equity (dollar-neutral-ish).
    Returns metrics (total return, round trips, win rate, profit factor,
    max drawdown, Sharpe).
    """
    n = min(len(candles_a), len(candles_b))
    cash = start_equity
    pos = None              # None | 'long_a' | 'short_a'
    entry_a = entry_b = 0.0
    notional = 0.0
    equity_curve = []
    realized = []
    trades = []

    for i in range(strategy.warmup, n):
        action, z = strategy.signal(candles_a[: i + 1], candles_b[: i + 1])
        pa = candles_a[i][4]
        pb = candles_b[i][4]

        def pnl_of():
            ra = pa / entry_a - 1.0
            rb = pb / entry_b - 1.0
            if pos == "long_a":
                return notional * (ra - rb)
            return notional * (rb - ra)

        if pos is None:
            if action in ("long_a", "short_a"):
                notional = cash * leg_pct
                cash -= 2 * notional * fee_pct  # entry fees on both legs
                pos = action
                entry_a, entry_b = pa, pb
                trades.append(("enter", action, pa, pb))
        else:
            should_exit = (action == "flat") or \
                (action in ("long_a", "short_a") and action != pos)
            if should_exit:
                pnl = pnl_of()
                cash += pnl - 2 * notional * fee_pct  # exit fees on both legs
                realized.append(pnl)
                trades.append(("exit", pos, pa, pb, pnl))
                pos = None
                if action in ("long_a", "short_a"):
                    notional = cash * leg_pct
                    cash -= 2 * notional * fee_pct
                    pos = action
                    entry_a, entry_b = pa, pb
                    trades.append(("enter", action, pa, pb))

        eq = cash + (pnl_of() if pos is not None else 0.0)
        equity_curve.append(eq)

    # Close any open position at the end of the series.
    if pos is not None:
        pa, pb = candles_a[n - 1][4], candles_b[n - 1][4]
        pnl = pnl_of()
        cash += pnl - 2 * notional * fee_pct
        realized.append(pnl)
        trades.append(("exit", pos, pa, pb, pnl))
        pos = None

    return _pairs_metrics(start_equity, cash, realized, equity_curve)


def _pairs_metrics(start, final_equity, realized, equity_curve) -> dict:
    total_return = (final_equity / start - 1.0) * 100
    wins = sum(1 for p in realized if p > 0)
    round_trips = len(realized)
    win_rate = (wins / round_trips * 100) if round_trips else 0.0
    gross_profit = sum(p for p in realized if p > 0)
    gross_loss = abs(sum(p for p in realized if p < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    peak = -float("inf")
    max_dd = 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak)

    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i - 1] > 0:
            returns.append(equity_curve[i] / equity_curve[i - 1] - 1.0)
    sharpe = 0.0
    if returns:
        mean = sum(returns) / len(returns)
        std = math.sqrt(sum((r - mean) ** 2 for r in returns) / len(returns))
        sharpe = (mean / std * math.sqrt(252)) if std > 0 else 0.0

    return {
        "total_return_pct": total_return,
        "final_equity": final_equity,
        "round_trips": round_trips,
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_dd * 100,
        "sharpe": sharpe,
    }


def backtest_pairs(config: dict, limit: int, fee_pct: float) -> dict:
    p = pair_settings(config)
    leg_a = p.get("leg_a", "QQQ")
    leg_b = p.get("leg_b", "SPY")
    timeframe = p.get("timeframe", "1d")
    feed = StockPriceFeed()
    strat = PairsTrading(
        window=p.get("window", 50),
        entry_z=p.get("entry_z", 2.0),
        exit_z=p.get("exit_z", 0.5),
    )
    ca = feed.fetch_ohlcv(leg_a, timeframe, limit=limit)
    cb = feed.fetch_ohlcv(leg_b, timeframe, limit=limit)
    if len(ca) < strat.warmup or len(cb) < strat.warmup:
        raise RuntimeError(f"Not enough data for pair {leg_a}/{leg_b}")
    return run_pairs_backtest(ca, cb, strat,
                              start_equity=config["paper"]["starting_balance"],
                              fee_pct=fee_pct,
                              leg_pct=p.get("leg_pct", 0.5))


# ---------------------------------------------------------------------------
# Live runner
# ---------------------------------------------------------------------------

def run_pairs_bot(config: dict) -> None:
    p = pair_settings(config)
    leg_a = p.get("leg_a", "QQQ")
    leg_b = p.get("leg_b", "SPY")
    timeframe = p.get("timeframe", "1d")
    interval = p.get("interval_seconds", 3600)
    fetch_limit = config.get("data", {}).get("fetch_limit", 500)

    log = setup_logger(
        level=config.get("logging", {}).get("level", "INFO"),
        log_file=config.get("logging", {}).get("file", "logs/trader.log"),
    )

    from dotenv import load_dotenv
    import os
    load_dotenv()
    broker = AlpacaBroker(
        api_key=os.getenv("ALPACA_API_KEY", ""),
        api_secret=os.getenv("ALPACA_API_SECRET", ""),
        paper=(config.get("mode", "alpaca_paper") == "alpaca_paper"),
    )
    strat = PairsTrading(
        window=p.get("window", 50),
        entry_z=p.get("entry_z", 2.0),
        exit_z=p.get("exit_z", 0.5),
    )
    leg_pct = p.get("leg_pct", 0.5)

    state = StateStore(config.get("state_file", "state.json"))
    state.data["pairs"] = {"leg_a": leg_a, "leg_b": leg_b}

    log.info("Pairs bot started | pair=%s/%s timeframe=%s", leg_a, leg_b, timeframe)

    while True:
        try:
            ca = broker.fetch_ohlcv(leg_a, timeframe, limit=fetch_limit)
            cb = broker.fetch_ohlcv(leg_b, timeframe, limit=fetch_limit)
            if not ca or not cb:
                time.sleep(interval)
                continue

            action, z = strat.signal(ca, cb)
            pos_a = broker.get_position(leg_a).base_amount   # signed (neg = short)
            pos_b = broker.get_position(leg_b).base_amount

            # Current pair state inferred from broker positions.
            long_a = pos_a > 0 and pos_b < 0
            short_a = pos_a < 0 and pos_b > 0
            in_position = long_a or short_a
            current = "long_a" if long_a else ("short_a" if short_a else None)

            market_open = broker.market_open()

            if not in_position and action in ("long_a", "short_a") and market_open:
                equity = broker.equity(leg_a)
                notional = equity * leg_pct
                if action == "long_a":
                    broker.market_buy(leg_a, notional)
                    broker.market_sell_short(leg_b, notional)
                else:
                    broker.market_sell_short(leg_a, notional)
                    broker.market_buy(leg_b, notional)
                log.info("PAIRS ENTER %s | z=%.2f | %s long, %s short",
                         action, z, leg_a if action == "long_a" else leg_b,
                         leg_b if action == "long_a" else leg_a)

            elif in_position and (action == "flat" or
                                  (action in ("long_a", "short_a") and action != current)):
                broker.close_position(leg_a)
                broker.close_position(leg_b)
                log.info("PAIRS EXIT %s | z=%.2f", current, z)

            state.data["pairs"]["z_score"] = round(z, 2) if z is not None else None
            state.data["pairs"]["action"] = action
            state.data["pairs"]["position"] = current
            state.data["pairs"]["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            state.save()

        except Exception as e:
            log.error("pairs loop error: %s", e)

        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pairs trading runner")
    parser.add_argument("--backtest", action="store_true", help="run a backtest")
    parser.add_argument("--limit", type=int, default=1000, help="candles for backtest")
    parser.add_argument("--fee", type=float, default=None, help="override fee rate")
    parser.add_argument("--config", default="config.yaml", help="config file path")
    args = parser.parse_args()

    config = load_config(args.config)
    fee = args.fee if args.fee is not None else config["paper"]["fee_pct"]

    if args.backtest:
        p = pair_settings(config)
        print(f"Backtesting pairs {p.get('leg_a')}/{p.get('leg_b')} "
              f"({p.get('timeframe')}, {args.limit} candles, fee={fee:.4f})...\n")
        result = backtest_pairs(config, args.limit, fee)
        print(f"  Total return:      {result['total_return_pct']:+.2f}%")
        print(f"  Final equity:      ${result['final_equity']:,.2f}")
        print(f"  Round trips:       {result['round_trips']}")
        print(f"  Win rate:          {result['win_rate_pct']:.1f}%")
        print(f"  Profit factor:     {result['profit_factor']:.2f}")
        print(f"  Max drawdown:      {result['max_drawdown_pct']:.2f}%")
        print(f"  Sharpe (annual):   {result['sharpe']:.2f}")
    else:
        run_pairs_bot(config)


if __name__ == "__main__":
    main()
