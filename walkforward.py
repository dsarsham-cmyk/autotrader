"""Walk-forward optimization to avoid overfitting.

Walk-forward splits data into rolling in-sample (train) / out-of-sample (test)
windows. For each window it grid-searches strategy parameters on the train
portion, then applies the best parameters to the unseen test portion. The
aggregate out-of-sample performance is what matters — a strategy that only
looks good in-sample is overfit.

Usage:
    python walkforward.py --limit 2000 --folds 5
"""
from __future__ import annotations

import argparse
import itertools

import yaml

from strategy import TrendFollowing, build_strategy
from price_feed import build_price_feed
from risk import RiskConfig, RiskManager
from backtest import load_config, market_settings, risk_config, run_simulation


# Parameter grid for the trend-following strategy.
GRID = {
    "fast_period": [10, 20, 30],
    "slow_period": [40, 50, 60],
    "trend_period": [100, 200],
}


def _param_combos(grid: dict) -> list[dict]:
    keys = list(grid.keys())
    return [dict(zip(keys, vals)) for vals in itertools.product(*grid.values())]


def walk_forward(config: dict, limit: int, fee_pct: float, folds: int) -> dict:
    symbols, timeframe = market_settings(config)
    symbol = symbols[0]
    feed = build_price_feed(config["market"], config["exchange"]["name"])
    candles = feed.fetch_ohlcv(symbol, timeframe, limit=limit)
    if len(candles) < 300:
        raise RuntimeError(f"Not enough data for {symbol}: {len(candles)} candles")

    start_equity = config["paper"]["starting_balance"]
    risk_cfg = risk_config(config)

    # Split into `folds` equal segments; each fold is out-of-sample once.
    seg = len(candles) // folds
    oos_results = []
    chosen_params = []

    for f in range(1, folds):
        train = candles[: f * seg]
        test = candles[f * seg: (f + 1) * seg]
        if len(train) < 300 or len(test) < 60:
            continue

        best = None
        best_score = -float("inf")
        for combo in _param_combos(GRID):
            strat = TrendFollowing(**combo)
            risk = RiskManager(risk_cfg)
            m = run_simulation(train, strat, risk, fee_pct, start_equity,
                               min_history=strat.warmup)
            # Score = return penalized by drawdown (avoid overfit to one metric).
            score = m["total_return_pct"] - m["max_drawdown_pct"]
            if score > best_score:
                best_score = score
                best = combo

        # Apply best params to the unseen test segment.
        strat = TrendFollowing(**best)
        risk = RiskManager(risk_cfg)
        m = run_simulation(test, strat, risk, fee_pct, start_equity,
                           min_history=strat.warmup)
        m["params"] = best
        oos_results.append(m)
        chosen_params.append(best)

    if not oos_results:
        raise RuntimeError("Not enough data for walk-forward analysis")

    # Aggregate out-of-sample performance.
    total_ret = sum(r["total_return_pct"] for r in oos_results)
    avg_win = sum(r["win_rate_pct"] for r in oos_results) / len(oos_results)
    avg_dd = sum(r["max_drawdown_pct"] for r in oos_results) / len(oos_results)
    avg_sharpe = sum(r["sharpe"] for r in oos_results) / len(oos_results)

    return {
        "folds": len(oos_results),
        "oos_total_return_pct": total_ret,
        "oos_avg_win_rate_pct": avg_win,
        "oos_avg_max_dd_pct": avg_dd,
        "oos_avg_sharpe": avg_sharpe,
        "chosen_params": chosen_params,
        "detail": oos_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward optimization")
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--fee", type=float, default=None)
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    fee = args.fee if args.fee is not None else config["paper"]["fee_pct"]
    symbols, timeframe = market_settings(config)
    symbol = symbols[0]

    print(f"Walk-forward on {symbol} ({timeframe}, {args.limit} candles, "
          f"{args.folds} folds)...\n")

    result = walk_forward(config, args.limit, fee, args.folds)

    print(f"  Out-of-sample total return: {result['oos_total_return_pct']:+.2f}%")
    print(f"  Out-of-sample avg win rate: {result['oos_avg_win_rate_pct']:.1f}%")
    print(f"  Out-of-sample avg max DD:   {result['oos_avg_max_dd_pct']:.2f}%")
    print(f"  Out-of-sample avg Sharpe:   {result['oos_avg_sharpe']:.2f}")
    print(f"\n  Chosen parameters per fold:")
    for i, p in enumerate(result["chosen_params"], 1):
        print(f"    fold {i}: {p}")


if __name__ == "__main__":
    main()
