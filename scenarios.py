"""Compare risk scenarios for the day-trading strategy.

Runs volume_breakout on the leveraged ETFs under different risk settings and
reports the honest tradeoff: monthly return vs. max drawdown.

Usage:
    python scenarios.py
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
FEE = 0.001

SCENARIOS = {
    "A - Aggressive (5x risk)": RiskConfig(
        risk_per_trade=0.05, atr_stop_mult=2.0, atr_take_mult=3.0,
        max_position_pct=1.0, daily_loss_limit_pct=0.05, max_drawdown_pct=0.30,
    ),
    "B - Max leverage (10x risk)": RiskConfig(
        risk_per_trade=0.10, atr_stop_mult=1.5, atr_take_mult=3.0,
        max_position_pct=1.0, daily_loss_limit_pct=0.08, max_drawdown_pct=0.40,
    ),
}


def months_in(candles) -> float:
    if len(candles) < 2:
        return 0.0
    return (candles[-1][0] - candles[0][0]) / (30.44 * 24 * 3600 * 1000)


def main():
    feed = StockPriceFeed()
    print("Fetching data...")
    soxl = feed.fetch_ohlcv("SOXL", "1h", 2000)
    tqqq = feed.fetch_ohlcv("TQQQ", "1h", 2000)

    strat = build_strategy({"name": "volume_breakout", "lookback": 10, "vol_mult": 2.0})

    print(f"\nvolume_breakout | 1h | close-at-EOD | fee {FEE*100:.1f}% | start 10,000\n")
    print(f"{'Scenario':<28} {'Sym':<6} {'Period':>6} {'Total%':>8} "
          f"{'1mo%':>7} {'10k->1mo':>10} {'MaxDD%':>8} {'Trades':>6}")
    print("-" * 90)

    for label, risk in SCENARIOS.items():
        for sym, candles in (("SOXL", soxl), ("TQQQ", tqqq)):
            rm = RiskManager(risk)
            r = run_simulation(candles, strat, rm, FEE, START, strat.warmup,
                               close_at_eod=True)
            m = months_in(candles)
            monthly = r["total_return_pct"] / m if m > 0 else 0.0
            after = START * (1 + monthly / 100.0)
            print(f"{label:<28} {sym:<6} {m:>6.1f} {r['total_return_pct']:>+8.2f} "
                  f"{monthly:>+7.2f} {after:>10,.0f} {r['max_drawdown_pct']:>8.2f} "
                  f"{r['round_trips']:>6}")


if __name__ == "__main__":
    main()
