"""Compare multiple strategies (and/or tickers) on historical data.

Usage:
    python compare.py                        # all strategies on configured symbol
    python compare.py --symbols AAPL MSFT SPY
    python compare.py --limit 1000

Prints a ranked table of total return, win rate, and max drawdown.
"""
from __future__ import annotations

import argparse

import yaml

from strategy import STRATEGIES
from backtest import backtest, market_settings


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare strategies/tickers")
    parser.add_argument("--symbols", nargs="*", default=None, help="tickers to test")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    fee = config["paper"]["fee_pct"]
    base_symbols, timeframe = market_settings(config)
    symbols = args.symbols or base_symbols

    rows = []
    for symbol in symbols:
        for strat_name in STRATEGIES:
            cfg = dict(config)
            cfg["strategy"] = {"name": strat_name}
            # Apply sensible defaults for each strategy.
            if strat_name == "moving_average_crossover":
                cfg["strategy"].update(fast_period=20, slow_period=50)
            elif strat_name == "rsi":
                cfg["strategy"].update(period=14, oversold=30, overbought=70)
            elif strat_name == "bollinger_bands":
                cfg["strategy"].update(period=20, num_std=2.0)
            elif strat_name == "macd":
                cfg["strategy"].update(fast_period=12, slow_period=26, signal_period=9)
            elif strat_name == "trend_following":
                cfg["strategy"].update(fast_period=20, slow_period=50, trend_period=200)

            # Point the config at the symbol under test.
            if config["market"] == "crypto":
                cfg["exchange"]["symbol"] = symbol
            elif config["market"] == "stock":
                cfg["stock"]["symbol"] = symbol
            elif config["market"] == "forex":
                cfg["forex"]["symbol"] = symbol

            try:
                r = backtest(cfg, args.limit, fee)
            except Exception as e:
                print(f"  skip {symbol}/{strat_name}: {e}")
                continue
            rows.append({
                "symbol": symbol,
                "strategy": strat_name,
                "return": r["total_return_pct"],
                "win_rate": r["win_rate_pct"],
                "max_dd": r["max_drawdown_pct"],
                "sharpe": r["sharpe"],
            })

    rows.sort(key=lambda x: x["return"], reverse=True)

    print(f"\n{'Symbol':<10} {'Strategy':<26} {'Return%':>9} {'WinRate%':>9} "
          f"{'MaxDD%':>8} {'Sharpe':>7}")
    print("-" * 75)
    for r in rows:
        print(f"{r['symbol']:<10} {r['strategy']:<26} {r['return']:>9.2f} "
              f"{r['win_rate']:>9.1f} {r['max_dd']:>8.2f} {r['sharpe']:>7.2f}")


if __name__ == "__main__":
    main()
