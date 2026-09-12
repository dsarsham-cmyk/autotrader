"""Backtesting engine with volatility-adjusted sizing and intra-bar stops.

Usage:
    python backtest.py                 # uses config.yaml settings
    python backtest.py --limit 1000 --fee 0.001
    python backtest.py --save results.json

Simulates a long-only strategy with ATR-based position sizing, stop-loss and
take-profit (checked intra-bar using high/low), and realistic fees.
"""
from __future__ import annotations

import argparse
import json
import math

import yaml

from strategy import Signal, build_strategy, atr, day_of, clear_indicators
from price_feed import build_price_feed
from risk import RiskConfig, RiskManager


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def market_settings(config: dict) -> tuple[list[str], str]:
    """Return (list of symbols, timeframe) from config."""
    market = config["market"]
    if market == "crypto":
        return [config["exchange"]["symbol"]], config["exchange"]["timeframe"]
    if market == "stock":
        symbols = config["stock"].get("symbols")
        if not symbols:
            symbols = [config["stock"].get("symbol", "SPY")]
        return list(symbols), config["stock"]["timeframe"]
    if market == "forex":
        return [config["forex"]["symbol"]], config["forex"]["timeframe"]
    raise ValueError(f"Unknown market: {market!r}")


def risk_config(config: dict) -> RiskConfig:
    r = config.get("risk", {})
    return RiskConfig(
        risk_per_trade=r.get("risk_per_trade", 0.01),
        atr_stop_mult=r.get("atr_stop_mult", 2.0),
        atr_take_mult=r.get("atr_take_mult", 3.0),
        max_position_pct=r.get("max_position_pct", 0.25),
        daily_loss_limit_pct=r.get("daily_loss_limit_pct", 0.03),
        max_drawdown_pct=r.get("max_drawdown_pct", 0.20),
    )


def run_simulation(candles, strategy, risk: RiskManager, fee_pct: float,
                   start_equity: float, min_history: int,
                   close_at_eod: bool = False) -> dict:
    """Core simulation loop over an in-memory candle list. Returns metrics.

    If close_at_eod is True, any open position is closed at the last bar of
    each trading day (day-trading mode — no overnight positions).
    """
    clear_indicators()
    atr_series = atr(candles, period=14)
    cash = start_equity
    base = 0.0
    entry_price = 0.0
    stop_price = 0.0
    take_price = 0.0
    equity_curve = []
    trades = []
    realized_pnl = []

    # Incrementally grow the candle window instead of re-slicing the full list
    # on every bar (which made this loop O(n^2)). At iteration i the window is
    # exactly `candles[:i + 1]`, so strategy.evaluate() sees identical input.
    window = candles[:min_history]

    for i in range(min_history, len(candles)):
        window.append(candles[i])
        o, h, l, c = candles[i][1], candles[i][2], candles[i][3], candles[i][4]

        # Intra-bar stop / take profit while holding.
        if base > 0:
            exit_price = None
            if l <= stop_price:
                exit_price = stop_price
            elif h >= take_price:
                exit_price = take_price
            if exit_price is not None:
                gross = base * exit_price
                cash += gross - gross * fee_pct
                realized_pnl.append(gross - base * entry_price)
                trades.append(("sell", exit_price, gross))
                base = 0.0
                entry_price = 0.0

        signal = strategy.evaluate(window)

        if signal == Signal.BUY and base <= 0 and risk.allow_trading():
            a = atr_series[i]
            units = risk.position_size(cash, c, a)
            if units > 0:
                cost = units * c
                fee = cost * fee_pct
                cash -= cost + fee
                base = units
                entry_price = c
                stop_price, take_price = risk.stops(c, a)
                trades.append(("buy", c, cost))

        elif signal == Signal.SELL and base > 0:
            gross = base * c
            cash += gross - gross * fee_pct
            realized_pnl.append(gross - base * entry_price)
            trades.append(("sell", c, gross))
            base = 0.0
            entry_price = 0.0

        # End-of-day close (day trading): close any open position on the
        # last bar of the day.
        if close_at_eod and base > 0:
            last_of_day = (i == len(candles) - 1) or \
                (day_of(candles[i + 1][0]) != day_of(candles[i][0]))
            if last_of_day:
                gross = base * c
                cash += gross - gross * fee_pct
                realized_pnl.append(gross - base * entry_price)
                trades.append(("sell", c, gross))
                base = 0.0
                entry_price = 0.0

        equity = cash + base * c
        equity_curve.append(equity)
        risk.update_equity(equity, day_key=day_of(candles[i][0]))

    final_price = candles[-1][4]
    if base > 0:
        gross = base * final_price
        cash += gross - gross * fee_pct
        realized_pnl.append(gross - base * entry_price)
        trades.append(("sell", final_price, gross))
        base = 0.0
    final_equity = cash

    return _metrics(start_equity, final_equity, trades, realized_pnl,
                    equity_curve, candles, final_price)


def backtest(config: dict, limit: int, fee_pct: float, close_at_eod: bool = False) -> dict:
    symbols, timeframe = market_settings(config)
    symbol = symbols[0]
    feed = build_price_feed(config["market"], config["exchange"]["name"])
    strategy = build_strategy(config["strategy"])
    risk = RiskManager(risk_config(config))

    candles = feed.fetch_ohlcv(symbol, timeframe, limit=limit)
    if len(candles) < 60:
        raise RuntimeError(f"Not enough data for {symbol}: {len(candles)} candles")

    return run_simulation(candles, strategy, risk, fee_pct,
                          config["paper"]["starting_balance"], strategy.warmup,
                          close_at_eod=close_at_eod)


def _metrics(start, final_equity, trades, realized_pnl, equity_curve, candles, final_price):
    total_return = (final_equity / start - 1.0) * 100

    wins = sum(1 for p in realized_pnl if p > 0)
    round_trips = len(realized_pnl)
    win_rate = (wins / round_trips * 100) if round_trips else 0.0

    gross_profit = sum(p for p in realized_pnl if p > 0)
    gross_loss = abs(sum(p for p in realized_pnl if p < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    peak = -float("inf")
    max_dd = 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak)

    buy_hold = (final_price / candles[0][4] - 1.0) * 100
    sharpe, sortino = _risk_adjusted(equity_curve)

    return {
        "total_return_pct": total_return,
        "final_equity": final_equity,
        "num_trades": len(trades),
        "round_trips": round_trips,
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_dd * 100,
        "buy_hold_return_pct": buy_hold,
        "sharpe": sharpe,
        "sortino": sortino,
    }


def _risk_adjusted(equity_curve) -> tuple[float, float]:
    if len(equity_curve) < 3:
        return 0.0, 0.0
    returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]
        if prev > 0:
            returns.append(equity_curve[i] / prev - 1.0)
    if not returns:
        return 0.0, 0.0
    mean = sum(returns) / len(returns)
    std = math.sqrt(sum((r - mean) ** 2 for r in returns) / len(returns))
    sharpe = (mean / std * math.sqrt(252)) if std > 0 else 0.0
    downside = [r for r in returns if r < 0]
    if downside:
        dstd = math.sqrt(sum(r ** 2 for r in downside) / len(returns))
        sortino = (mean / dstd * math.sqrt(252)) if dstd > 0 else 0.0
    else:
        sortino = 0.0
    return sharpe, sortino


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the configured strategy")
    parser.add_argument("--limit", type=int, default=1000, help="number of candles")
    parser.add_argument("--fee", type=float, default=None, help="override fee rate")
    parser.add_argument("--config", default="config.yaml", help="config file path")
    parser.add_argument("--save", default=None, help="save results to JSON")
    parser.add_argument("--close-eod", action="store_true",
                        help="close positions at end of day (day trading)")
    args = parser.parse_args()

    config = load_config(args.config)
    fee = args.fee if args.fee is not None else config["paper"]["fee_pct"]
    symbols, timeframe = market_settings(config)
    symbol = symbols[0]

    print(f"Backtesting {config['strategy']['name']} on {symbol} "
          f"({timeframe}, {args.limit} candles, fee={fee:.4f})...\n")

    result = backtest(config, args.limit, fee, close_at_eod=args.close_eod)
    result.update(symbol=symbol, strategy=config["strategy"]["name"], timeframe=timeframe)

    print(f"  Total return:      {result['total_return_pct']:+.2f}%")
    print(f"  Final equity:      ${result['final_equity']:,.2f}")
    print(f"  Buy & hold return: {result['buy_hold_return_pct']:+.2f}%")
    print(f"  Round trips:       {result['round_trips']}")
    print(f"  Win rate:          {result['win_rate_pct']:.1f}%")
    print(f"  Profit factor:     {result['profit_factor']:.2f}")
    print(f"  Max drawdown:      {result['max_drawdown_pct']:.2f}%")
    print(f"  Sharpe (annual):   {result['sharpe']:.2f}")
    print(f"  Sortino (annual):  {result['sortino']:.2f}")

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"\nSaved results to {args.save}")


if __name__ == "__main__":
    main()
