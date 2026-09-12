"""Estimate 1-month returns for a 10k investment across all strategies.

Backtests each strategy over a recent period and reports:
  - total return over the period
  - average monthly return (total / months)
  - estimated value of 10,000 after 1 month (linear, NOT a guarantee)

Usage:
    python estimate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from strategy import build_strategy
from price_feed import StockPriceFeed
from backtest import run_simulation
from risk import RiskConfig, RiskManager

START = 10000.0
FEE = 0.001  # 0.1% per side (conservative; Alpaca is $0 commission)

RISK = RiskConfig(
    risk_per_trade=0.01, atr_stop_mult=2.0, atr_take_mult=3.0,
    max_position_pct=0.25, daily_loss_limit_pct=0.03, max_drawdown_pct=0.20,
)


def months_in(candles) -> float:
    """Approximate number of months spanned by a candle series."""
    if len(candles) < 2:
        return 0.0
    span_ms = candles[-1][0] - candles[0][0]
    return span_ms / (30.44 * 24 * 3600 * 1000)  # avg month in ms


def run(name, params, candles, close_at_eod, fee=FEE):
    strat = build_strategy({"name": name, **params})
    risk = RiskManager(RISK)
    r = run_simulation(candles, strat, risk, fee, START, strat.warmup,
                       close_at_eod=close_at_eod)
    m = months_in(candles)
    monthly = (r["total_return_pct"] / m) if m > 0 else 0.0
    after_1m = START * (1 + monthly / 100.0)
    return {
        "strategy": name,
        "params": params,
        "total_return_pct": r["total_return_pct"],
        "months": m,
        "monthly_pct": monthly,
        "after_1m": after_1m,
        "win_rate_pct": r["win_rate_pct"],
        "profit_factor": r["profit_factor"],
        "max_drawdown_pct": r["max_drawdown_pct"],
        "round_trips": r["round_trips"],
    }


def main():
    feed = StockPriceFeed()
    print("Fetching data...")
    qqq_1h = feed.fetch_ohlcv("QQQ", "1h", 2000)
    tqqq_1h = feed.fetch_ohlcv("TQQQ", "1h", 2000)
    qqq_1d = feed.fetch_ohlcv("QQQ", "1d", 750)
    spy_1d = feed.fetch_ohlcv("SPY", "1d", 750)

    rows = []

    # --- Day-trading strategies (1h, close at EOD) ---
    day = [
        ("intraday_momentum", {"fast_period": 5, "slow_period": 15}),
        ("intraday_momentum", {"fast_period": 3, "slow_period": 10}),
        ("opening_range_breakout", {"or_bars": 2}),
    ]
    for name, params in day:
        for sym, candles in (("QQQ", qqq_1h), ("TQQQ", tqqq_1h)):
            r = run(name, params, candles, close_at_eod=True)
            r["symbol"] = sym
            rows.append(r)

    # --- Swing strategies (1d, hold overnight) ---
    swing = [
        ("donchian_breakout", {"entry_period": 20, "exit_period": 10}),
        ("trend_following", {"fast_period": 20, "slow_period": 50, "trend_period": 200}),
        ("time_series_momentum", {"lookback": 252}),
        ("volatility_scaled_momentum", {"lookback": 252, "vol_period": 20,
                                        "vol_baseline": 252, "vol_mult": 2.0}),
        ("regime_adaptive", {"fast_period": 20, "slow_period": 50}),
        ("moving_average_crossover", {"fast_period": 20, "slow_period": 50}),
        ("macd", {}),
    ]
    for name, params in swing:
        for sym, candles in (("QQQ", qqq_1d), ("SPY", spy_1d)):
            r = run(name, params, candles, close_at_eod=False)
            r["symbol"] = sym
            rows.append(r)

    # Print table.
    print(f"\n{'Strategy':<28} {'Sym':<6} {'Period':>5} {'Total%':>8} "
          f"{'1mo%':>7} {'10k->':>9} {'Win%':>6} {'PF':>5} {'MaxDD%':>7}")
    print("-" * 100)
    for r in sorted(rows, key=lambda x: -x["monthly_pct"]):
        params_s = ",".join(f"{k}={v}" for k, v in r["params"].items())
        label = f"{r['strategy']}" + (f"({params_s})" if params_s else "")
        print(f"{label:<28} {r['symbol']:<6} {r['months']:>5.1f} "
              f"{r['total_return_pct']:>+8.2f} {r['monthly_pct']:>+7.2f} "
              f"{r['after_1m']:>9,.0f} {r['win_rate_pct']:>6.1f} "
              f"{r['profit_factor']:>5.2f} {r['max_drawdown_pct']:>7.2f}")


if __name__ == "__main__":
    main()
