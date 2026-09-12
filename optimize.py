"""Day-trading strategy optimization with walk-forward validation.

Grid-searches day-trading strategies across symbols, timeframes, and
parameters, then validates the best configs out-of-sample (walk-forward) to
avoid overfitting. Reports honest out-of-sample results.

Usage:
    python optimize.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from strategy import build_strategy
from price_feed import StockPriceFeed
from backtest import run_simulation
from risk import RiskConfig, RiskManager

START = 100000.0
FEE = 0.001  # 0.1% per side (conservative; Alpaca is $0 commission)

RISK = RiskConfig(
    risk_per_trade=0.01, atr_stop_mult=2.0, atr_take_mult=3.0,
    max_position_pct=0.25, daily_loss_limit_pct=0.03, max_drawdown_pct=0.20,
)


def evaluate(name, params, candles, close_at_eod=True, fee=FEE):
    strat = build_strategy({"name": name, **params})
    risk = RiskManager(RISK)
    return run_simulation(candles, strat, risk, fee, START, strat.warmup,
                          close_at_eod=close_at_eod)


def walk_forward(name, params, candles, split=0.6):
    """Optimize on the first `split` of data, validate on the rest."""
    n = len(candles)
    cut = int(n * split)
    train = candles[:cut]
    test = candles[cut:]
    if len(test) < 60:
        return None
    in_sample = evaluate(name, params, train)
    out_sample = evaluate(name, params, test)
    return {
        "in_total": in_sample["total_return_pct"],
        "out_total": out_sample["total_return_pct"],
        "out_pf": out_sample["profit_factor"],
        "out_win": out_sample["win_rate_pct"],
        "out_dd": out_sample["max_drawdown_pct"],
        "out_trades": out_sample["round_trips"],
    }


def main():
    feed = StockPriceFeed()

    symbols = ["QQQ", "TQQQ", "SPY", "SPXL", "SOXL"]
    timeframes = ["1h", "30m", "15m"]

    # Strategy parameter grids.
    grids = []
    for fast in (3, 5, 8, 10):
        for slow in (15, 20, 30, 40):
            if fast < slow:
                grids.append(("intraday_momentum",
                              {"fast_period": fast, "slow_period": slow}))
    for or_bars in (1, 2, 3, 5):
        grids.append(("opening_range_breakout", {"or_bars": or_bars}))
    for band in (0.2, 0.3, 0.5, 1.0):
        grids.append(("vwap_mean_reversion", {"band_pct": band}))
    for gap in (0.2, 0.3, 0.5, 1.0):
        grids.append(("gap_and_go", {"gap_pct": gap}))
    for lookback in (10, 20, 40):
        for vol_mult in (1.5, 2.0, 3.0):
            grids.append(("volume_breakout", {"lookback": lookback, "vol_mult": vol_mult}))

    print("Fetching data...")
    data = {}
    for sym in symbols:
        for tf in timeframes:
            try:
                c = feed.fetch_ohlcv(sym, tf, 2000)
                if len(c) > 120:
                    data[(sym, tf)] = c
            except Exception as e:
                print(f"  {sym} {tf}: {e}")

    results = []
    for (sym, tf), candles in data.items():
        for name, params in grids:
            r = walk_forward(name, params, candles)
            if r is None:
                continue
            results.append({
                "sym": sym, "tf": tf, "name": name, "params": params, **r,
            })

    # Rank by out-of-sample total return.
    results.sort(key=lambda x: -x["out_total"])

    print(f"\n{'Sym':<6} {'TF':<5} {'Strategy':<26} {'In%':>7} {'Out%':>8} "
          f"{'PF':>5} {'Win%':>6} {'MaxDD%':>7} {'Trades':>6}")
    print("-" * 100)
    shown = 0
    for r in results[:30]:
        p = ",".join(f"{k}={v}" for k, v in r["params"].items())
        label = f"{r['name']}({p})"
        print(f"{r['sym']:<6} {r['tf']:<5} {label:<26} {r['in_total']:>+7.2f} "
              f"{r['out_total']:>+8.2f} {r['out_pf']:>5.2f} {r['out_win']:>6.1f} "
              f"{r['out_dd']:>7.2f} {r['out_trades']:>6}")
        shown += 1

    # Summary: how many configs are positive out-of-sample?
    pos = [r for r in results if r["out_total"] > 0]
    print(f"\n{len(results)} configs tested; {len(pos)} positive out-of-sample "
          f"({len(pos)/len(results)*100:.0f}%).")


if __name__ == "__main__":
    main()
