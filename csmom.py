"""Cross-sectional momentum (CSMOM) — a portfolio-level strategy.

Unlike the single-asset strategies in strategy.py, cross-sectional momentum
ranks a broad universe of assets by their trailing return and goes long the
winners / short the losers. This is the most robust, well-documented anomaly
in finance (Jegadeesh & Titman 1993; Moskowitz, Ooi & Pedersen 2012; AQR
"Century of Evidence"), and it is fundamentally different from time-series
momentum (which bets on one asset continuing its own trend).

Design
------
- Universe: ~44 liquid ETFs spanning US equity, sectors, international equity,
  fixed income, commodities, and real estate.
- Signal: trailing return over `lookback` trading days, skipping the most
  recent `skip` days (to avoid the short-term reversal effect). Standard is
  "12-1" (lookback 252 days, skip 21 days).
- Portfolio: long the top `top_k`, short the bottom `top_k`, equal weight,
  rebalanced every `rebalance_every` trading days (monthly).
- Costs: fee on turnover (0.1% per side, conservative; Alpaca is $0 commission
  but there is spread/slippage and short-borrow cost).

Usage
-----
    python csmom.py                  # full backtest + report
    python csmom.py --sweep          # parameter sweep (robustness)
    python csmom.py --walk-forward   # walk-forward validation
    python csmom.py --long-only      # long-only variant (no shorting)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Universe: broad, liquid ETFs across asset classes
# ---------------------------------------------------------------------------

UNIVERSE = [
    # US broad equity
    "SPY", "QQQ", "DIA", "IWM", "MDY", "IJR",
    # US sectors (SPDR)
    "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE",
    # International equity
    "EFA", "EEM", "EWJ", "EWG", "EWU", "EWC", "EWZ", "EWH", "EWY", "EWA",
    "EWQ", "EWP", "EWS",
    # Fixed income
    "TLT", "IEF", "SHY", "LQD", "HYG", "AGG", "TIP", "EMB",
    # Commodities
    "GLD", "SLV", "USO", "DBC", "GDX",
    # Real estate
    "VNQ", "IYR",
]

# Liquid US large-cap stocks (the right universe for cross-sectional momentum:
# high cross-sectional dispersion, unlike diversified ETFs).
STOCK_UNIVERSE = [
    # Technology
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "ORCL",
    "CRM", "ADBE", "CSCO", "INTC", "AMD", "QCOM", "TXN", "INTU", "NOW",
    "IBM", "ACN", "ADI", "MU", "AMAT", "LRCX", "KLAC", "PANW", "SNPS",
    "CDNS", "ANET", "PLTR", "UBER", "SHOP", "NET", "DDOG", "CRWD",
    # Financials
    "JPM", "BAC", "WFC", "GS", "MS", "C", "SCHW", "BLK", "AXP", "V",
    "MA", "PYPL", "COF", "USB", "PNC",
    # Healthcare
    "JNJ", "UNH", "PFE", "MRK", "ABBV", "LLY", "TMO", "ABT", "DHR",
    "BMY", "GILD", "AMGN", "ISRG", "ELV", "CI", "MDT", "SYK", "BSX",
    "VRTX", "REGN",
    # Consumer
    "PG", "KO", "PEP", "COST", "WMT", "HD", "MCD", "NKE", "SBUX", "TGT",
    "LOW", "CL", "KMB", "GIS", "MO", "PM", "DIS", "CMCSA", "NFLX",
    "BKNG", "MAR", "ABNB", "TSLA", "F", "GM",
    # Industrials
    "GE", "CAT", "DE", "HON", "BA", "LMT", "RTX", "UPS", "FDX", "UNP",
    "CSX", "NSC", "EMR", "ETN", "ITW", "MMM", "WM", "RSG",
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "PSX", "MPC", "VLO", "OXY",
    # Materials
    "LIN", "APD", "SHW", "FCX", "NEM", "ECL", "DD", "DOW",
    # Utilities
    "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE",
    # Real estate
    "AMT", "PLD", "CCI", "EQIX", "SPG", "PSA", "O",
]

BENCHMARK = "SPY"

# 3x leveraged ETFs — the highest-octane retail-accessible universe. Momentum
# rotation across these produces high returns but with brutal drawdowns.
# Includes international 3x ETFs (Europe, Emerging, China) for global exposure.
LEVERAGED_UNIVERSE = [
    # US (3x long)
    "TQQQ", "SOXL", "SPXL", "TNA", "UDOW", "FAS", "ERX", "TECL",
    "CURE", "LABU", "FNGU", "NAIL",
    # International 3x (US-listed, tradeable on Alpaca)
    "EURL", "EDC", "YINN",
]


def fetch(symbols: list[str], period: str = "10y") -> pd.DataFrame:
    """Download adjusted-close prices for a list of symbols, aligned by date.

    Returns a DataFrame indexed by date with one column per symbol.
    """
    import yfinance as yf
    df = yf.download(symbols, period=period, interval="1d",
                     auto_adjust=True, progress=False, group_by="column")
    if isinstance(df.columns, pd.MultiIndex):
        close = df["Close"]
    else:
        close = df
    close = close.dropna(how="all")
    return close


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

def momentum_scores(close: pd.DataFrame, lookback: int, skip: int) -> pd.DataFrame:
    """Trailing return from t-lookback to t-skip (skips recent reversal)."""
    return close.shift(skip) / close.shift(lookback) - 1.0


def composite_scores(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
                     lookback: int = 21, range_period: int = 20) -> pd.DataFrame:
    """Average of cross-sectional range-rank and momentum-rank.

    Discovered empirically (IC +0.048 for intraday range vs next-day return):
    expanding intraday range predicts higher forward returns. Blending the
    range rank with the momentum rank gives a more robust signal than either
    alone (lower drawdown, positive in all walk-forward folds).
    """
    rng = (high - low) / close
    rng_avg = rng.rolling(range_period).mean()
    mom = close.pct_change(lookback)
    r_rank = rng_avg.rank(axis=1, pct=True)
    m_rank = mom.rank(axis=1, pct=True)
    return (r_rank + m_rank) / 2.0


def backtest_csmom(close: pd.DataFrame, lookback: int = 252, skip: int = 21,
                   top_k: int = 10, fee: float = 0.001,
                   rebalance_every: int = 21, long_only: bool = False,
                   bench: pd.Series | None = None) -> dict:
    """Simulate a cross-sectional momentum portfolio.

    Returns a dict with metrics and the portfolio equity curve (Series).
    """
    returns = close.pct_change(fill_method=None)
    scores = momentum_scores(close, lookback, skip)

    n = len(close)
    cols = close.columns
    positions = pd.DataFrame(0.0, index=close.index, columns=cols)

    weights = pd.Series(0.0, index=cols)
    for i in range(lookback, n):
        if (i - lookback) % rebalance_every == 0:
            s = scores.iloc[i].dropna()
            if len(s) >= 2 * top_k:
                ranked = s.sort_values(ascending=False)
                longs = ranked.index[:top_k]
                shorts = ranked.index[-top_k:]
                w = 1.0 / (2 * top_k)
                new_weights = pd.Series(0.0, index=cols)
                new_weights.loc[longs] = w
                if not long_only:
                    new_weights.loc[shorts] = -w
                weights = new_weights
        positions.iloc[i] = weights

    # Daily portfolio return = (yesterday's weights) * (today's asset returns).
    port_returns = (positions.shift(1).fillna(0.0) * returns.fillna(0.0)).sum(axis=1)

    # Fees on turnover (only non-zero on rebalance days).
    turnover = positions.diff().abs().sum(axis=1)
    port_returns = port_returns - turnover * fee

    equity = (1.0 + port_returns).cumprod()
    equity = equity / equity.iloc[0]

    # Benchmark: buy-and-hold SPY (passed in, or equal-weight universe fallback).
    if bench is None:
        if BENCHMARK in close.columns:
            bench = close[BENCHMARK] / close[BENCHMARK].iloc[0]
        else:
            bench = (close / close.iloc[0]).mean(axis=1)
    bench = bench.reindex(close.index).ffill()

    return {
        "equity": equity,
        "benchmark": bench,
        "returns": port_returns,
        "metrics": _metrics(equity, port_returns, bench),
    }


def _metrics(equity: pd.Series, returns: pd.Series,
             bench: pd.Series) -> dict:
    """Compute performance metrics for a portfolio equity curve."""
    total = (equity.iloc[-1] - 1.0) * 100
    years = len(equity) / 252.0
    cagr = (equity.iloc[-1] ** (1.0 / years) - 1.0) * 100 if years > 0 else 0.0

    r = returns.dropna()
    if len(r) > 1:
        ann_vol = r.std() * np.sqrt(252) * 100
        sharpe = (r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0
        downside = r[r < 0]
        dstd = np.sqrt((downside ** 2).sum() / len(r))
        sortino = (r.mean() / dstd * np.sqrt(252)) if dstd > 0 else 0.0
    else:
        ann_vol = sharpe = sortino = 0.0

    peak = equity.cummax()
    drawdown = (equity / peak - 1.0)
    max_dd = drawdown.min() * 100

    bench_total = (bench.iloc[-1] - 1.0) * 100

    return {
        "total_return_pct": total,
        "cagr_pct": cagr,
        "annual_vol_pct": ann_vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown_pct": max_dd,
        "benchmark_return_pct": bench_total,
        "excess_vs_benchmark_pct": total - bench_total,
        "years": years,
    }


def _print_metrics(label: str, m: dict) -> None:
    print(f"\n{label}")
    print("-" * 60)
    print(f"  Total return:        {m['total_return_pct']:+.2f}%  "
          f"({m['years']:.1f} yrs)")
    print(f"  CAGR (annualized):   {m['cagr_pct']:+.2f}%")
    print(f"  Annual volatility:   {m['annual_vol_pct']:.2f}%")
    print(f"  Sharpe:              {m['sharpe']:.2f}")
    print(f"  Sortino:             {m['sortino']:.2f}")
    print(f"  Max drawdown:        {m['max_drawdown_pct']:.2f}%")
    print(f"  Benchmark (SPY):     {m['benchmark_return_pct']:+.2f}%")
    print(f"  Excess vs benchmark: {m['excess_vs_benchmark_pct']:+.2f}%")


# ---------------------------------------------------------------------------
# Parameter sweep (robustness)
# ---------------------------------------------------------------------------

def sweep(close: pd.DataFrame, long_only: bool = False) -> None:
    mode = "long-only" if long_only else "long-short"
    print(f"Parameter sweep (full-period backtest, {mode}):\n")
    print(f"{'lookback':>8} {'skip':>5} {'top_k':>6} {'CAGR%':>8} {'Sharpe':>7} "
          f"{'MaxDD%':>8}")
    print("-" * 60)
    for lookback in (126, 252, 504):
        for skip in (0, 21):
            for top_k in (5, 10, 20):
                r = backtest_csmom(close, lookback=lookback, skip=skip,
                                   top_k=top_k, long_only=long_only)
                m = r["metrics"]
                print(f"{lookback:>8} {skip:>5} {top_k:>6} {m['cagr_pct']:>+8.2f} "
                      f"{m['sharpe']:>7.2f} {m['max_drawdown_pct']:>8.2f}")


# ---------------------------------------------------------------------------
# Walk-forward validation
# ---------------------------------------------------------------------------

def walk_forward(close: pd.DataFrame, folds: int = 4,
                 long_only: bool = False) -> None:
    """Walk-forward: optimize params on train, apply to unseen test."""
    mode = "long-only" if long_only else "long-short"
    print(f"\nWalk-forward validation ({folds} folds, {mode}):\n")
    n = len(close)
    seg = n // folds
    print(f"{'fold':>4} {'lookback':>8} {'skip':>5} {'top_k':>6} "
          f"{'OOS CAGR%':>9} {'OOS Sharpe':>10} {'OOS MaxDD%':>10}")
    print("-" * 60)
    for f in range(1, folds):
        train = close.iloc[: f * seg]
        test = close.iloc[f * seg: (f + 1) * seg]
        if len(test) < 252:
            continue
        best = None
        best_score = -float("inf")
        for lookback in (126, 252):
            for skip in (0, 21):
                for top_k in (5, 10, 20):
                    r = backtest_csmom(train, lookback=lookback, skip=skip,
                                       top_k=top_k, long_only=long_only)
                    score = r["metrics"]["sharpe"]
                    if score > best_score:
                        best_score = score
                        best = (lookback, skip, top_k)
        r = backtest_csmom(test, lookback=best[0], skip=best[1], top_k=best[2],
                           long_only=long_only)
        m = r["metrics"]
        print(f"{f:>4} {best[0]:>8} {best[1]:>5} {best[2]:>6} "
              f"{m['cagr_pct']:>+9.2f} {m['sharpe']:>10.2f} "
              f"{m['max_drawdown_pct']:>10.2f}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-sectional momentum")
    parser.add_argument("--sweep", action="store_true")
    parser.add_argument("--walk-forward", action="store_true")
    parser.add_argument("--long-only", action="store_true")
    parser.add_argument("--stocks", action="store_true",
                        help="use the individual-stock universe instead of ETFs")
    parser.add_argument("--lookback", type=int, default=252)
    parser.add_argument("--skip", type=int, default=21)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--period", default="10y")
    args = parser.parse_args()

    universe = STOCK_UNIVERSE if args.stocks else UNIVERSE
    print(f"Fetching {len(universe)} {'stocks' if args.stocks else 'ETFs'} ({args.period}) ...")
    close = fetch(universe, period=args.period)
    print(f"  {close.shape[0]} trading days, {close.shape[1]} symbols "
          f"({close.index[0].date()} -> {close.index[-1].date()})")

    # Benchmark: SPY buy-and-hold (fetched separately so it is always the
    # market benchmark, regardless of whether SPY is in the trading universe).
    spy = fetch([BENCHMARK], period=args.period)
    bench = spy[BENCHMARK] / spy[BENCHMARK].iloc[0]

    if args.sweep:
        sweep(close, long_only=args.long_only)
        return
    if args.walk_forward:
        walk_forward(close, long_only=args.long_only)
        return

    r = backtest_csmom(close, lookback=args.lookback, skip=args.skip,
                       top_k=args.top_k, long_only=args.long_only, bench=bench)
    label = f"Cross-sectional momentum ({'long-only' if args.long_only else 'long-short'}, "
    label += f"lookback={args.lookback}, skip={args.skip}, top_k={args.top_k})"
    _print_metrics(label, r["metrics"])


if __name__ == "__main__":
    main()
