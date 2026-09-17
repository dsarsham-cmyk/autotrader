"""Portfolio-level backtest for the two live scenarios (HIGH / LOW risk).

Faithfully mirrors the live bot so results are directly comparable to what the
deployed system does:

  * same strategy (``volatility_scaled_momentum``),
  * same ATR-based position sizing,
  * same ``capital_fraction`` + **total-deployment cap** (the fix that stops
    the two scenarios over-leveraging one shared paper account),
  * same stop-loss / take-profit / trailing-stop exit plan,
  * realistic fees.

It runs on historical *daily* bars (via yfinance, free public data) so the
numbers are trustworthy and free of paper-account glitches (stray positions,
phantom equity jumps, etc.).

Usage:
    python scenario_backtest.py                # both scenarios, ~6 years
    python scenario_backtest.py --years 10     # longer history
    python scenario_backtest.py --save results.json
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import yaml

from strategy import Signal, build_strategy, atr, day_of, clear_indicators
from price_feed import StockPriceFeed
from risk import RiskConfig, RiskManager

STARTING_BALANCE = 100_000.0
FEE_PCT = 0.001  # 10 bps round-trip approximation for ETF fills


def load_config(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def risk_config(config: dict) -> RiskConfig:
    r = config.get("risk", {})
    return RiskConfig(
        risk_per_trade=r.get("risk_per_trade", 0.01),
        atr_stop_mult=r.get("atr_stop_mult", 2.0),
        atr_take_mult=r.get("atr_take_mult", 3.0),
        max_position_pct=r.get("max_position_pct", 0.25),
        daily_loss_limit_pct=r.get("daily_loss_limit_pct", 0.03),
        max_drawdown_pct=r.get("max_drawdown_pct", 0.20),
        break_even_atr=r.get("break_even_atr", 1.0),
        trail_atr=r.get("trail_atr", 2.0),
        trail_distance_atr=r.get("trail_distance_atr", 1.0),
        capital_fraction=r.get("capital_fraction", 1.0),
    )


def _align(candles_by_symbol: dict) -> tuple[list[str], dict]:
    """Return (sorted list of unique trading days, {symbol: {day: candle}})."""
    all_days = set()
    for candles in candles_by_symbol.values():
        for c in candles:
            all_days.add(day_of(c[0]))
    days = sorted(all_days)
    by_sym = {
        s: {day_of(c[0]): c for c in candles}
        for s, candles in candles_by_symbol.items()
    }
    return days, by_sym


def run_portfolio(candles_by_symbol: dict, strategy_cfg: dict, rc: RiskConfig,
                  fee_pct: float, start_equity: float) -> dict:
    """Simulate one scenario's portfolio over a common daily calendar.

    Returns metrics plus a per-symbol breakdown.
    """
    clear_indicators()
    days, by_sym = _align(candles_by_symbol)
    symbols = list(candles_by_symbol.keys())
    strategies = {s: build_strategy(strategy_cfg) for s in symbols}
    risk = RiskManager(rc)

    windows = {s: [] for s in symbols}
    pos = {s: {"base": 0.0, "entry": 0.0, "stop": 0.0, "take": 0.0,
               "trail_high": 0.0} for s in symbols}

    cash = start_equity
    equity_curve = []
    realized = []          # realized P&L per closed trade
    trades = []            # (side, symbol, price, qty)
    per_symbol_pnl = {s: 0.0 for s in symbols}

    for day in days:
        # Portfolio equity at the start of this day (cash + open positions at
        # today's close). Used once per day for all sizing decisions, matching
        # the live bot which computes equity once per loop iteration.
        equity = cash
        for s in symbols:
            c = by_sym[s].get(day)
            if c is not None and pos[s]["base"] > 0:
                equity += pos[s]["base"] * c[4]
        risk.update_equity(equity, day)

        # Total notional currently deployed (cost basis), for the cap.
        deployed = sum(pos[s]["base"] * pos[s]["entry"]
                       for s in symbols if pos[s]["base"] > 0)

        for s in symbols:
            c = by_sym[s].get(day)
            if c is None:
                continue
            windows[s].append(c)
            o, h, l, cl = c[1], c[2], c[3], c[4]
            st = strategies[s]
            p = pos[s]

            # --- Intra-bar stop / take profit (matches Alpaca bracket orders) ---
            if p["base"] > 0:
                exit_price = None
                if p["stop"] > 0 and l <= p["stop"]:
                    exit_price = p["stop"]
                elif p["take"] > 0 and h >= p["take"]:
                    exit_price = p["take"]
                if exit_price is not None:
                    gross = p["base"] * exit_price
                    cash += gross - gross * fee_pct
                    pnl = gross - p["base"] * p["entry"]
                    realized.append(pnl)
                    per_symbol_pnl[s] += pnl
                    trades.append(("sell", s, exit_price, p["base"]))
                    p["base"] = p["entry"] = p["stop"] = p["take"] = p["trail_high"] = 0.0

            signal = st.evaluate(windows[s])
            a = atr(windows[s], 14)[-1]

            # --- Trailing stop (lock in profits) ---
            if p["base"] > 0:
                # The live bot polls throughout the session and therefore sees
                # prices above the daily close.  Use the bar high here so the
                # backtest does not systematically understate trailing-stop
                # activation.  The revised stop applies from the next bar;
                # OHLC data cannot tell whether today's high happened before
                # or after today's low, so a same-bar fill would add look-ahead.
                p["trail_high"] = max(p["trail_high"], h)
                new_stop = risk.trailing_stop(p["entry"], p["trail_high"], a, p["stop"])
                if new_stop > p["stop"]:
                    p["stop"] = new_stop

            # --- Strategy signals ---
            if risk.allow_trading():
                if signal == Signal.BUY and p["base"] <= 0:
                    units = risk.position_size(equity, cl, a)
                    if units > 0:
                        notional = units * cl
                        cap = equity * rc.capital_fraction
                        if deployed + notional > cap:
                            # Total-deployment cap reached: skip this entry.
                            pass
                        else:
                            cost = notional
                            fee = cost * fee_pct
                            cash -= cost + fee
                            p["base"] = units
                            p["entry"] = cl
                            p["stop"], p["take"] = risk.stops(cl, a)
                            p["trail_high"] = cl
                            deployed += notional
                            trades.append(("buy", s, cl, units))
                elif signal == Signal.SELL and p["base"] > 0:
                    gross = p["base"] * cl
                    cash += gross - gross * fee_pct
                    pnl = gross - p["base"] * p["entry"]
                    realized.append(pnl)
                    per_symbol_pnl[s] += pnl
                    trades.append(("sell", s, cl, p["base"]))
                    p["base"] = p["entry"] = p["stop"] = p["take"] = p["trail_high"] = 0.0

        # End-of-day equity (mark open positions to today's close).
        eod_equity = cash
        for s in symbols:
            c = by_sym[s].get(day)
            if c is not None and pos[s]["base"] > 0:
                eod_equity += pos[s]["base"] * c[4]
        equity_curve.append(eod_equity)

    # Close any remaining open positions at the last available close.
    final_equity = cash
    for s in symbols:
        if pos[s]["base"] > 0:
            last = candles_by_symbol[s][-1][4]
            gross = pos[s]["base"] * last
            final_equity += gross - gross * fee_pct
            pnl = gross - pos[s]["base"] * pos[s]["entry"]
            realized.append(pnl)
            per_symbol_pnl[s] += pnl

    metrics = _metrics(start_equity, final_equity, realized, equity_curve, days)
    metrics["per_symbol_pnl"] = {s: round(v, 2) for s, v in per_symbol_pnl.items()}
    metrics["num_trades"] = len(trades)
    return metrics


def _metrics(start, final_equity, realized, equity_curve, days) -> dict:
    total_return = (final_equity / start - 1.0) * 100

    # Annualized (CAGR) from the number of trading days (~252/year).
    years = max(len(days) / 252.0, 1e-9)
    cagr = ((final_equity / start) ** (1.0 / years) - 1.0) * 100 if final_equity > 0 else -100.0

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

    sharpe, sortino = _risk_adjusted(equity_curve)

    return {
        "total_return_pct": round(total_return, 2),
        "annualized_return_pct": round(cagr, 2),
        "final_equity": round(final_equity, 2),
        "round_trips": round_trips,
        "win_rate_pct": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else None,
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
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


def fetch_symbols(symbols: list[str], years: int) -> dict:
    """Fetch `years` of daily bars for each symbol via yfinance."""
    feed = StockPriceFeed()
    limit = int(years * 252) + 60
    out = {}
    for s in symbols:
        candles = feed.fetch_ohlcv(s, "1d", limit=limit)
        if len(candles) < 300:
            print(f"  ! {s}: only {len(candles)} bars (skipping)")
            continue
        out[s] = candles
        print(f"  {s}: {len(candles)} bars")
    return out


def backtest_scenario(config_path: str, years: int) -> dict:
    cfg = load_config(config_path)
    symbols = cfg["stock"]["symbols"]
    rc = risk_config(cfg)
    strategy_cfg = cfg["strategy"]

    print(f"\n=== {cfg.get('name', config_path)} ===")
    print(f"  symbols: {', '.join(symbols)}")
    print(f"  strategy: {strategy_cfg['name']} | capital_fraction={rc.capital_fraction} "
          f"| risk_per_trade={rc.risk_per_trade}")

    candles_by_symbol = fetch_symbols(symbols, years)
    if not candles_by_symbol:
        raise RuntimeError(f"No data fetched for {config_path}")

    result = run_portfolio(candles_by_symbol, strategy_cfg, rc, FEE_PCT, STARTING_BALANCE)
    result["name"] = cfg.get("name", config_path)
    result["symbols"] = list(candles_by_symbol.keys())
    result["capital_fraction"] = rc.capital_fraction
    result["risk_per_trade"] = rc.risk_per_trade
    result["strategy"] = strategy_cfg["name"]
    return result


def _print(result: dict) -> None:
    print(f"\n  Total return:       {result['total_return_pct']:+.2f}%")
    print(f"  Annualized (CAGR):  {result['annualized_return_pct']:+.2f}%")
    print(f"  Final equity:       ${result['final_equity']:,.2f}")
    print(f"  Round trips:        {result['round_trips']}")
    print(f"  Win rate:           {result['win_rate_pct']:.1f}%")
    pf = result["profit_factor"]
    print(f"  Profit factor:      {'inf' if pf is None else f'{pf:.2f}'}")
    print(f"  Max drawdown:       {result['max_drawdown_pct']:.2f}%")
    print(f"  Sharpe (annual):    {result['sharpe']:.2f}")
    print(f"  Sortino (annual):   {result['sortino']:.2f}")
    print(f"  Per-symbol P&L:     {result['per_symbol_pnl']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Portfolio backtest for both scenarios")
    parser.add_argument("--years", type=int, default=6, help="years of history")
    parser.add_argument("--save", default=None, help="save results to JSON")
    args = parser.parse_args()

    scenarios = [("config_high.yaml",), ("config_low.yaml",)]
    results = {}
    for (cfg,) in scenarios:
        r = backtest_scenario(cfg, args.years)
        _print(r)
        results[cfg] = r

    if args.save:
        Path(args.save).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nSaved results to {args.save}")


if __name__ == "__main__":
    main()
