"""Rank all strategies by risk-adjusted, out-of-sample performance.

For each strategy it runs walk-forward validation: the data is split into
chronological folds, and each fold is tested on data the strategy has never
seen (out-of-sample). This measures how the strategy would have performed
going forward, not how well it was curve-fit to the past.

Usage:
    python rank.py --limit 2000 --folds 4
    python rank.py --symbols AAPL MSFT SPY QQQ --limit 2000

Ranking is by Sortino ratio (return per unit of downside risk), with Sharpe,
max drawdown, profit factor, and win rate shown for context.
"""
from __future__ import annotations

import argparse

import yaml

from strategy import STRATEGIES
from price_feed import build_price_feed
from risk import RiskManager
from backtest import load_config, market_settings, risk_config, run_simulation


def walk_forward_strategy(strategy, candles, folds, fee_pct, start_equity, risk_cfg):
    """Run walk-forward for one strategy and aggregate out-of-sample metrics."""
    seg = len(candles) // folds
    oos = []
    for f in range(1, folds):
        test = candles[f * seg: (f + 1) * seg]
        if len(test) < 60:
            continue
        # Warmup = enough history before the test segment for indicators.
        warmup = candles[max(0, f * seg - strategy.warmup): f * seg]
        data = warmup + test
        risk = RiskManager(risk_cfg)
        m = run_simulation(data, strategy, risk, fee_pct, start_equity, strategy.warmup)
        oos.append(m)
    return oos


def aggregate(oos_list):
    """Aggregate out-of-sample metrics across folds."""
    if not oos_list:
        return None
    n = len(oos_list)
    total_ret = sum(m["total_return_pct"] for m in oos_list)
    win = sum(m["win_rate_pct"] for m in oos_list) / n
    dd = sum(m["max_drawdown_pct"] for m in oos_list) / n
    sharpe = sum(m["sharpe"] for m in oos_list) / n
    sortino = sum(m["sortino"] for m in oos_list) / n
    pf = sum(m["profit_factor"] for m in oos_list if m["profit_factor"] != float("inf")) / n
    trips = sum(m["round_trips"] for m in oos_list)
    return {
        "total_return_pct": total_ret,
        "win_rate_pct": win,
        "max_drawdown_pct": dd,
        "sharpe": sharpe,
        "sortino": sortino,
        "profit_factor": pf,
        "round_trips": trips,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank strategies by risk")
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--fee", type=float, default=None)
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    fee = args.fee if args.fee is not None else config["paper"]["fee_pct"]
    start_equity = config["paper"]["starting_balance"]
    risk_cfg = risk_config(config)
    base_symbols, timeframe = market_settings(config)
    symbols = args.symbols or base_symbols

    feed = build_price_feed(config["market"], config["exchange"]["name"])

    # Aggregate each strategy's out-of-sample metrics across all symbols.
    agg_by_strategy = {}
    for name, cls in STRATEGIES.items():
        strat = cls()
        all_oos = []
        for symbol in symbols:
            candles = feed.fetch_ohlcv(symbol, timeframe, limit=args.limit)
            if len(candles) < 300:
                continue
            all_oos.extend(walk_forward_strategy(strat, candles, args.folds, fee, start_equity, risk_cfg))
        agg_by_strategy[name] = aggregate(all_oos)

    # Rank by Sortino (downside-risk-adjusted return).
    ranked = sorted(
        [(name, m) for name, m in agg_by_strategy.items() if m],
        key=lambda x: x[1]["sortino"],
        reverse=True,
    )

    print(f"\nRanking {len(ranked)} strategies on {', '.join(symbols)} "
          f"({timeframe}, {args.limit} candles, {args.folds} walk-forward folds)\n")
    print(f"{'#':<3} {'Strategy':<24} {'Sortino':>8} {'Sharpe':>7} {'MaxDD%':>8} "
          f"{'PF':>6} {'Win%':>7} {'OOS Ret%':>9} {'Trades':>7}")
    print("-" * 85)
    for i, (name, m) in enumerate(ranked, 1):
        print(f"{i:<3} {name:<24} {m['sortino']:>8.2f} {m['sharpe']:>7.2f} "
              f"{m['max_drawdown_pct']:>8.2f} {m['profit_factor']:>6.2f} "
              f"{m['win_rate_pct']:>7.1f} {m['total_return_pct']:>+9.2f} "
              f"{m['round_trips']:>7}")

    print("\nRanking is by Sortino ratio (return per unit of downside risk).")
    print("Higher Sortino = better risk-adjusted out-of-sample performance.")


if __name__ == "__main__":
    main()
