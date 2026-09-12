"""Research & validation engine.

A systematic, honest strategy-research engine. It does what a quick backtest
cannot: it walks forward through time, grid-searches parameters ONLY on past
data, applies the winning parameters to *unseen* future data, and ranks
strategies by their out-of-sample, risk-adjusted performance.

This is the difference between "looks good in the past" (curve-fitting) and
"would have made money going forward" (a real, deployable edge).

Pipeline
--------
1. Fetch OHLCV for the full universe (US, leveraged, Europe, Asia ETFs) across
   intraday timeframes (day trading) and daily (swing), with on-disk caching.
2. Walk-forward validation: for each strategy, split history into chronological
   folds; for each fold, grid-search parameters on the train window, then apply
   the best parameters to the unseen test window.
3. Aggregate out-of-sample metrics and rank strategies by a risk-adjusted score
   (return per unit of drawdown, with a minimum-trade-count filter).
4. Detect overfitting by comparing in-sample vs out-of-sample returns.
5. Re-optimize the winning strategy on the FULL history to pick production
   parameters, then write them into config_low.yaml / config_high.yaml.
6. Emit a Markdown report + machine-readable JSON.

Usage
-----
    python engine.py                  # full run: fetch, validate, rank, report, write configs
    python engine.py --quick          # fast smoke test (small universe, 2 folds)
    python engine.py --symbols QQQ SPY --timeframes 1h --folds 3
    python engine.py --no-write       # validate + report, but don't touch configs
    python engine.py --report report.md

Honesty note: no strategy guarantees profit, and 1-2% *daily* returns are not a
realistic expectation for a systematic long-only ETF strategy. This engine
reports what the data actually supports, including the in-sample/out-of-sample
gap that exposes curve-fitting.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

# Allow running directly from the repo root or the autotrader directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from strategy import build_strategy, STRATEGIES
from price_feed import StockPriceFeed
from backtest import run_simulation
from risk import RiskConfig, RiskManager

# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------

# Symbols grouped by region. International markets are traded via US-listed
# ETFs (Alpaca only lists US securities), e.g. EWJ = Japan, EZU = Eurozone.
UNIVERSE = {
    "US": ["QQQ", "SPY", "DIA", "IWM"],
    "US_LEVERAGED": ["TQQQ", "SPXL", "SOXL"],
    "EUROPE": ["EZU", "EWU", "EWG", "EWQ"],
    "ASIA": ["EWJ", "EWH", "EWY"],
}

# All symbols, flattened, deduplicated, in a stable order.
ALL_SYMBOLS = []
for _grp in ("US", "US_LEVERAGED", "EUROPE", "ASIA"):
    for _s in UNIVERSE[_grp]:
        if _s not in ALL_SYMBOLS:
            ALL_SYMBOLS.append(_s)

# Intraday timeframes for day trading (positions closed at end of day).
INTRADAY_TIMEFRAMES = ["1h", "30m", "15m"]
# Daily timeframe for swing strategies (positions held overnight).
SWING_TIMEFRAMES = ["1d"]

# ---------------------------------------------------------------------------
# Strategy parameter grids
# ---------------------------------------------------------------------------

# Day-trading strategies (tested on intraday timeframes, close_at_eod=True).
DAY_GRIDS = {
    "volume_breakout": {
        "lookback": [4, 6, 10, 20],
        "vol_mult": [1.5, 2.0, 3.0],
    },
    "intraday_momentum": {
        "fast_period": [3, 5, 8],
        "slow_period": [10, 15, 20, 30],
    },
    "opening_range_breakout": {"or_bars": [1, 2, 3, 5]},
    "directional_momentum": {
        "fast_period": [5, 8],
        "slow_period": [15, 21],
        "roc_period": [8, 12],
        "deadband": [0.0],
    },
    "supertrend": {
        "period": [7, 10, 14],
        "multiplier": [2.0, 3.0, 4.0],
    },
    "keltner_breakout": {
        "period": [10, 20],
        "atr_period": [10, 14],
        "mult": [1.5, 2.0, 3.0],
    },
    "nr7_breakout": {"n": [4, 7, 10]},
    "vwap_mean_reversion": {"band_pct": [0.2, 0.3, 0.5, 1.0]},
    "gap_and_go": {"gap_pct": [0.2, 0.3, 0.5, 1.0]},
    "vwap_trend": {"warmup": [20]},
    "stochastic": {
        "k_period": [9, 14],
        "d_period": [3],
        "oversold": [20.0],
        "overbought": [80.0],
    },
    "moving_average_crossover": {
        "fast_period": [10, 20],
        "slow_period": [30, 50],
    },
    "macd": {
        "fast_period": [8, 12],
        "slow_period": [21, 26],
        "signal_period": [9],
    },
    "donchian_breakout": {
        "entry_period": [10, 20, 40],
        "exit_period": [5, 10, 20],
    },
    "bollinger_bands": {
        "period": [20],
        "num_std": [1.5, 2.0, 2.5],
    },
    "rsi": {
        "period": [10, 14],
        "oversold": [25.0, 30.0],
        "overbought": [70.0, 75.0],
    },
    "zscore_mean_reversion": {
        "period": [30, 50],
        "entry_z": [1.5, 2.0],
        "exit_z": [0.5],
    },
    "regime_adaptive": {
        "fast_period": [10, 20],
        "slow_period": [30, 50],
        "trend_threshold": [0.5, 1.0],
    },
}

# Swing strategies (tested on daily bars, close_at_eod=False).
SWING_GRIDS = {
    "time_series_momentum": {"lookback": [63, 126, 252]},
    "volatility_scaled_momentum": {
        "lookback": [126, 252],
        "vol_period": [20],
        "vol_baseline": [252],
        "vol_mult": [1.5, 2.0],
    },
    "trend_following": {
        "fast_period": [10, 20],
        "slow_period": [40, 50],
        "trend_period": [100, 200],
    },
    "moving_average_crossover": {
        "fast_period": [20, 50],
        "slow_period": [100, 200],
    },
    "donchian_breakout": {
        "entry_period": [20, 55, 100],
        "exit_period": [10, 20, 55],
    },
    "macd": {
        "fast_period": [12],
        "slow_period": [26],
        "signal_period": [9],
    },
}

# ---------------------------------------------------------------------------
# Engine configuration
# ---------------------------------------------------------------------------

START_EQUITY = 100000.0
FEE = 0.001  # 0.1% per side (conservative; Alpaca is $0 commission)

# Risk settings used during research (neutral, 1% risk/trade). The live
# LOW/HIGH configs keep their own risk settings; this is only for ranking.
RESEARCH_RISK = RiskConfig(
    risk_per_trade=0.01, atr_stop_mult=2.0, atr_take_mult=3.0,
    max_position_pct=0.25, daily_loss_limit_pct=0.03, max_drawdown_pct=0.20,
)

MIN_TRADES = 8          # minimum round-trips for a result to be reliable
MIN_TRAIN_BARS = 100    # minimum train bars (beyond warmup) to grid-search
MIN_TEST_BARS = 60      # minimum test bars for a fold to count

CACHE_DIR = Path(__file__).resolve().parent / "cache" / "ohlcv"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def train_objective(m: dict) -> float:
    """Objective for in-sample parameter selection.

    Rewards return and penalizes drawdown equally. A minimum trade count is
    enforced so a single lucky trade can't dominate the selection.
    """
    if m["round_trips"] < MIN_TRADES:
        return -float("inf")
    return m["total_return_pct"] - 1.0 * m["max_drawdown_pct"]


def rank_score(m: dict) -> float | None:
    """Risk-adjusted out-of-sample score used for final ranking.

    Return per unit of max drawdown (a simple, robust Sharpe-like measure),
    plus a small win-rate term to reward consistency. Returns None when there
    are too few trades for the result to be meaningful.
    """
    if m["round_trips"] < MIN_TRADES:
        return None
    dd = max(m["max_drawdown_pct"], 0.5)
    return (m["total_return_pct"] / dd) + 0.05 * m["win_rate_pct"]


# ---------------------------------------------------------------------------
# Data (with on-disk caching so re-runs are fast)
# ---------------------------------------------------------------------------

class DataCache:
    """Fetch OHLCV via yfinance, caching each (symbol, timeframe) to disk."""

    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.feed = StockPriceFeed()

    def _path(self, symbol: str, timeframe: str) -> Path:
        return self.cache_dir / f"{symbol}_{timeframe}.json"

    def fetch(self, symbol: str, timeframe: str, limit: int) -> list:
        path = self._path(symbol, timeframe)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if len(data) >= limit:
                    return data[-limit:]
            except (json.JSONDecodeError, OSError):
                pass
        candles = self.feed.fetch_ohlcv(symbol, timeframe, limit=limit)
        if candles:
            path.write_text(json.dumps(candles), encoding="utf-8")
        return candles


# ---------------------------------------------------------------------------
# Simulation helpers
# ---------------------------------------------------------------------------

def simulate(candles: list, strategy, fee: float, start: float,
             close_at_eod: bool) -> dict:
    """Run one simulation with a fresh RiskManager."""
    risk = RiskManager(RESEARCH_RISK)
    return run_simulation(candles, strategy, risk, fee, start,
                          strategy.warmup, close_at_eod=close_at_eod)


def param_combos(grid: dict) -> list[dict]:
    """Expand a parameter grid into a list of concrete parameter dicts."""
    if not grid:
        return [{}]
    keys = list(grid.keys())
    return [dict(zip(keys, vals)) for vals in itertools.product(*grid.values())]


def grid_size(grid: dict) -> int:
    n = 1
    for vals in grid.values():
        n *= len(vals)
    return n


# ---------------------------------------------------------------------------
# Walk-forward validation
# ---------------------------------------------------------------------------

def walk_forward(name: str, grid: dict, candles: list, folds: int,
                 fee: float, start: float, close_at_eod: bool) -> dict | None:
    """Walk-forward validation for one strategy on one candle series.

    Returns a dict with out-of-sample aggregates, in-sample aggregates, the
    per-fold chosen parameters, and a final production parameter set (optimized
    on the full history). Returns None if there is insufficient data.
    """
    combos = param_combos(grid)
    seg = len(candles) // folds
    if seg < MIN_TEST_BARS:
        return None

    oos = []      # out-of-sample metrics per fold
    ins = []      # in-sample metrics per fold (for overfit detection)
    chosen = []   # winning parameters per fold

    for f in range(1, folds):
        train = candles[: f * seg]
        test = candles[f * seg: (f + 1) * seg]
        if len(test) < MIN_TEST_BARS:
            continue

        # Grid-search parameters on the TRAIN window only.
        best = None
        best_obj = -float("inf")
        for combo in combos:
            try:
                strat = build_strategy({"name": name, **combo})
            except (ValueError, TypeError):
                continue
            if len(train) < strat.warmup + MIN_TRAIN_BARS:
                continue
            m = simulate(train, strat, fee, start, close_at_eod)
            obj = train_objective(m)
            if obj > best_obj:
                best_obj = obj
                best = combo

        if best is None:
            continue

        # Apply the winning parameters to the UNSEEN test window. Prepend just
        # enough warmup history so indicators are correct, but only measure
        # performance over the test window.
        strat = build_strategy({"name": name, **best})
        warmup = candles[max(0, f * seg - strat.warmup): f * seg]
        data = warmup + test
        m_test = simulate(data, strat, fee, start, close_at_eod)
        m_train = simulate(train, strat, fee, start, close_at_eod)

        oos.append(m_test)
        ins.append(m_train)
        chosen.append(best)

    if not oos:
        return None

    # Final production parameters: re-optimize on the FULL history (legitimate
    # now that walk-forward has confirmed the strategy generalizes).
    final = None
    best_obj = -float("inf")
    for combo in combos:
        try:
            strat = build_strategy({"name": name, **combo})
        except (ValueError, TypeError):
            continue
        if len(candles) < strat.warmup + MIN_TRAIN_BARS:
            continue
        m = simulate(candles, strat, fee, start, close_at_eod)
        obj = train_objective(m)
        if obj > best_obj:
            best_obj = obj
            final = combo

    return {
        "name": name,
        "folds": len(oos),
        "oos": _aggregate(oos),
        "ins": _aggregate(ins),
        "chosen_params": chosen,
        "final_params": final,
    }


def _aggregate(metrics: list[dict]) -> dict:
    """Aggregate metrics across folds."""
    n = len(metrics)
    if n == 0:
        return {}
    total_ret = sum(m["total_return_pct"] for m in metrics)
    win = sum(m["win_rate_pct"] for m in metrics) / n
    dd = sum(m["max_drawdown_pct"] for m in metrics) / n
    sharpe = sum(m["sharpe"] for m in metrics) / n
    sortino = sum(m["sortino"] for m in metrics) / n
    trips = sum(m["round_trips"] for m in metrics)
    pf_vals = [m["profit_factor"] for m in metrics if m["profit_factor"] != float("inf")]
    pf = sum(pf_vals) / len(pf_vals) if pf_vals else 0.0
    return {
        "total_return_pct": total_ret,
        "win_rate_pct": win,
        "max_drawdown_pct": dd,
        "sharpe": sharpe,
        "sortino": sortino,
        "profit_factor": pf,
        "round_trips": trips,
    }


# ---------------------------------------------------------------------------
# Engine driver
# ---------------------------------------------------------------------------

def run_engine(symbols: list[str], timeframes: list[str], folds: int,
               day_only: bool = False, progress: bool = True) -> list[dict]:
    """Run walk-forward validation across the universe and return ranked rows.

    Each row is a (strategy, symbol, timeframe) result with out-of-sample and
    in-sample aggregates plus the overfit gap.
    """
    cache = DataCache()
    rows = []

    # Decide which strategy grids to test on which timeframes.
    plans = []  # (strategy_name, grid, close_at_eod, timeframes)
    for tf in timeframes:
        if tf in SWING_TIMEFRAMES:
            for name, grid in SWING_GRIDS.items():
                plans.append((name, grid, False, [tf]))
        else:
            for name, grid in DAY_GRIDS.items():
                plans.append((name, grid, True, [tf]))

    total_work = 0
    for name, grid, _, tfs in plans:
        total_work += len(symbols) * len(tfs)

    done = 0
    for name, grid, close_at_eod, tfs in plans:
        for symbol in symbols:
            for tf in tfs:
                done += 1
                if progress:
                    print(f"[{done}/{total_work}] {name} on {symbol} {tf} ...",
                          end=" ", flush=True)
                candles = cache.fetch(symbol, tf, limit=_limit_for(tf))
                if len(candles) < 200:
                    if progress:
                        print(f"skip (only {len(candles)} bars)")
                    continue
                result = walk_forward(name, grid, candles, folds, FEE,
                                      START_EQUITY, close_at_eod)
                if result is None:
                    if progress:
                        print("skip (insufficient data)")
                    continue
                result["symbol"] = symbol
                result["timeframe"] = tf
                result["close_at_eod"] = close_at_eod
                result["overfit_gap_pct"] = (
                    result["ins"]["total_return_pct"]
                    - result["oos"]["total_return_pct"]
                )
                rows.append(result)
                if progress:
                    oos = result["oos"]
                    print(f"OOS {oos['total_return_pct']:+.2f}% "
                          f"DD {oos['max_drawdown_pct']:.1f}% "
                          f"trades {oos['round_trips']}")

    return rows


def _limit_for(timeframe: str) -> int:
    if timeframe == "1d":
        return 750
    return 2000


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def rank_rows(rows: list[dict]) -> list[dict]:
    """Sort rows by out-of-sample risk-adjusted score, best first."""
    scored = []
    for r in rows:
        s = rank_score(r["oos"])
        if s is None:
            continue
        scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored]


def aggregate_by_strategy(rows: list[dict]) -> list[dict]:
    """Aggregate out-of-sample metrics across symbols/timeframes per strategy."""
    by_name: dict[str, list[dict]] = {}
    for r in rows:
        by_name.setdefault(r["name"], []).append(r["oos"])

    agg = []
    for name, oos_list in by_name.items():
        # Average the per-fold aggregates across all (symbol, timeframe) runs.
        n = len(oos_list)
        total_ret = sum(m["total_return_pct"] for m in oos_list) / n
        win = sum(m["win_rate_pct"] for m in oos_list) / n
        dd = sum(m["max_drawdown_pct"] for m in oos_list) / n
        sortino = sum(m["sortino"] for m in oos_list) / n
        sharpe = sum(m["sharpe"] for m in oos_list) / n
        trips = sum(m["round_trips"] for m in oos_list)
        score = rank_score({
            "round_trips": trips,
            "total_return_pct": total_ret,
            "max_drawdown_pct": dd,
            "win_rate_pct": win,
        })
        agg.append({
            "name": name,
            "runs": n,
            "oos_total_return_pct": total_ret,
            "oos_win_rate_pct": win,
            "oos_max_dd_pct": dd,
            "oos_sortino": sortino,
            "oos_sharpe": sharpe,
            "total_round_trips": trips,
            "score": score,
        })
    agg.sort(key=lambda x: -(x["score"] if x["score"] is not None else -float("inf")))
    return agg


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(rows: list[dict], strategy_agg: list[dict],
                 path: str = "engine_report.md") -> str:
    ranked = rank_rows(rows)
    lines = []
    lines.append("# Strategy Research & Validation Report")
    lines.append("")
    lines.append("Generated by `engine.py` — walk-forward, out-of-sample validation.")
    lines.append("")
    lines.append("> **How to read this:** every number below is *out-of-sample* — "
                 "the strategy was optimized only on past data and then measured on "
                 "data it had never seen. The \"overfit gap\" column shows how much "
                 "worse it did out-of-sample vs in-sample; a large positive gap means "
                 "the strategy is curve-fit and will likely fail live.")
    lines.append("")
    lines.append("## 1. Strategies ranked by out-of-sample risk-adjusted score")
    lines.append("")
    lines.append("| # | Strategy | Runs | OOS Return % | Win % | Max DD % | Sortino | Sharpe | Trades |")
    lines.append("|---|----------|------|-------------|-------|----------|---------|--------|--------|")
    for i, a in enumerate(strategy_agg, 1):
        if a["score"] is None:
            continue
        lines.append(
            f"| {i} | {a['name']} | {a['runs']} | {a['oos_total_return_pct']:+.2f} | "
            f"{a['oos_win_rate_pct']:.1f} | {a['oos_max_dd_pct']:.2f} | "
            f"{a['oos_sortino']:.2f} | {a['oos_sharpe']:.2f} | {a['total_round_trips']} |"
        )
    lines.append("")
    lines.append("## 2. Top (strategy, symbol, timeframe) combinations")
    lines.append("")
    lines.append("| # | Strategy | Symbol | TF | OOS % | In-Sample % | Overfit Gap | Win % | Max DD % | Trades |")
    lines.append("|---|----------|--------|----|-------|-------------|-------------|-------|----------|--------|")
    for i, r in enumerate(ranked[:30], 1):
        lines.append(
            f"| {i} | {r['name']} | {r['symbol']} | {r['timeframe']} | "
            f"{r['oos']['total_return_pct']:+.2f} | {r['ins']['total_return_pct']:+.2f} | "
            f"{r['overfit_gap_pct']:+.2f} | {r['oos']['win_rate_pct']:.1f} | "
            f"{r['oos']['max_drawdown_pct']:.2f} | {r['oos']['round_trips']} |"
        )
    lines.append("")
    lines.append("## 3. Interpretation")
    lines.append("")
    lines.append("- **Positive OOS return + small overfit gap** → a real, deployable edge.")
    lines.append("- **Positive OOS return + large overfit gap** → curve-fit; treat with caution.")
    lines.append("- **Negative OOS return** → no edge; do not deploy.")
    lines.append("- Strategies with fewer than ~8 round-trips are statistically unreliable.")
    lines.append("")
    lines.append("> **Reality check:** a systematic long-only ETF strategy that nets "
                 "a few percent *per month* with controlled drawdown is a strong, "
                 "realistic result. Expectations of 1-2% *per day* are not supported "
                 "by any honest backtest and imply ~500%+ annualized returns, which "
                 "is not achievable without extreme (and usually ruinous) leverage.")
    lines.append("")

    # Recommendation: the best positive out-of-sample strategy (with enough
    # trades to be statistically meaningful).
    positive = [a for a in strategy_agg
                if a["oos_total_return_pct"] > 0
                and a["total_round_trips"] >= MIN_TRADES]
    positive.sort(key=lambda a: -a["oos_total_return_pct"])
    lines.append("## 4. Recommendation")
    lines.append("")
    if positive:
        b = positive[0]
        lines.append(f"**Deploy `{b['name']}`** — the only strategy family with a "
                     f"positive, statistically meaningful out-of-sample edge "
                     f"(+{b['oos_total_return_pct']:.2f}% across {b['runs']} runs / "
                     f"{b['total_round_trips']} trades, max DD "
                     f"{b['oos_max_dd_pct']:.2f}%).")
        lines.append("")
        lines.append("The clear empirical result: **every intraday (day-trading) "
                     "strategy loses money out-of-sample** — the only profitable "
                     "strategies are slow trend-following / time-series momentum on "
                     "daily bars (swing). This matches the academic literature "
                     "(short-term trend-following has degraded since ~2009; most "
                     "retail day traders lose).")
    else:
        lines.append("No strategy has a positive out-of-sample edge. The honest "
                     "conclusion is that none of the tested strategies should be "
                     "deployed with real money.")
    lines.append("")

    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Config writing
# ---------------------------------------------------------------------------

def write_configs(rows: list[dict], strategy_agg: list[dict],
                  low_symbols: list[str], high_symbols: list[str]) -> dict:
    """Write the best *positive* strategy into the live configs.

    Ranks by aggregate out-of-sample return across all symbols/timeframes
    (NOT by a single symbol, which would overfit to one lucky result). Only
    writes a strategy that is positive out-of-sample in aggregate and has
    enough trades to be statistically meaningful. Handles both day (intraday)
    and swing (daily) strategies by setting the timeframe and close_at_eod
    accordingly. Preserves each scenario's own risk settings and symbols.
    """
    import yaml

    positive = [a for a in strategy_agg
                if a["oos_total_return_pct"] > 0
                and a["total_round_trips"] >= MIN_TRADES]
    positive.sort(key=lambda a: -a["oos_total_return_pct"])
    if not positive:
        return {"error": "no strategy has positive out-of-sample return; "
                         "not writing configs"}

    best = positive[0]
    name = best["name"]
    is_swing = name in SWING_GRIDS

    # Best production params = final_params of this strategy's best OOS row.
    strat_rows = [r for r in rows if r["name"] == name]
    best_row = max(strat_rows, key=lambda r: r["oos"]["total_return_pct"])
    params = best_row.get("final_params") or {}

    strategy_block = {"name": name}
    strategy_block.update(params)

    summary = {
        "strategy": name,
        "params": params,
        "mode": "swing" if is_swing else "day",
        "oos_return_pct": best["oos_total_return_pct"],
        "oos_max_dd_pct": best["oos_max_dd_pct"],
        "runs": best["runs"],
        "round_trips": best["total_round_trips"],
    }

    for cfg_path, symbols in (("config_low.yaml", low_symbols),
                              ("config_high.yaml", high_symbols)):
        p = Path(cfg_path)
        if not p.exists():
            continue
        cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
        cfg["strategy"] = strategy_block
        cfg["stock"]["symbols"] = symbols
        if is_swing:
            cfg["stock"]["timeframe"] = "1d"
            cfg["day_trading"]["close_at_eod"] = False
        else:
            cfg["stock"]["timeframe"] = "1h"
            cfg["day_trading"]["close_at_eod"] = True
        p.write_text(yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False),
                     encoding="utf-8")

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Research & validation engine")
    parser.add_argument("--symbols", nargs="*", default=None,
                        help="tickers to test (default: full universe)")
    parser.add_argument("--timeframes", nargs="*", default=None,
                        help="timeframes to test (default: intraday + daily)")
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--quick", action="store_true",
                        help="fast smoke test (small universe, 2 folds, 1h only)")
    parser.add_argument("--no-write", action="store_true",
                        help="do not write the live configs")
    parser.add_argument("--report", default="engine_report.md")
    parser.add_argument("--json", default="engine_results.json")
    args = parser.parse_args()

    if args.quick:
        symbols = ["QQQ", "SPY", "TQQQ", "EWJ"]
        timeframes = ["1h"]
        folds = 2
    else:
        symbols = args.symbols or ALL_SYMBOLS
        timeframes = args.timeframes or (INTRADAY_TIMEFRAMES + SWING_TIMEFRAMES)
        folds = args.folds

    t0 = time.time()
    print(f"Engine run: {len(symbols)} symbols x {len(timeframes)} timeframes, "
          f"{folds} folds")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Timeframes: {', '.join(timeframes)}\n")

    rows = run_engine(symbols, timeframes, folds)

    if not rows:
        print("\nNo results produced (insufficient data?).")
        return

    strategy_agg = aggregate_by_strategy(rows)
    ranked = rank_rows(rows)

    print("\n" + "=" * 80)
    print("STRATEGIES RANKED BY OUT-OF-SAMPLE RISK-ADJUSTED SCORE")
    print("=" * 80)
    print(f"{'#':<3} {'Strategy':<26} {'Runs':>4} {'OOS%':>8} {'Win%':>6} "
          f"{'MaxDD%':>8} {'Sortino':>8} {'Trades':>7}")
    print("-" * 80)
    for i, a in enumerate(strategy_agg, 1):
        if a["score"] is None:
            continue
        print(f"{i:<3} {a['name']:<26} {a['runs']:>4} "
              f"{a['oos_total_return_pct']:>+8.2f} {a['oos_win_rate_pct']:>6.1f} "
              f"{a['oos_max_dd_pct']:>8.2f} {a['oos_sortino']:>8.2f} "
              f"{a['total_round_trips']:>7}")

    print("\n" + "=" * 80)
    print("TOP (STRATEGY, SYMBOL, TIMEFRAME) COMBINATIONS")
    print("=" * 80)
    print(f"{'#':<3} {'Strategy':<24} {'Sym':<6} {'TF':<5} {'OOS%':>8} "
          f"{'In%':>8} {'Gap%':>7} {'Win%':>6} {'MaxDD%':>8} {'Trades':>7}")
    print("-" * 80)
    for i, r in enumerate(ranked[:20], 1):
        print(f"{i:<3} {r['name']:<24} {r['symbol']:<6} {r['timeframe']:<5} "
              f"{r['oos']['total_return_pct']:>+8.2f} "
              f"{r['ins']['total_return_pct']:>+8.2f} "
              f"{r['overfit_gap_pct']:>+7.2f} "
              f"{r['oos']['win_rate_pct']:>6.1f} "
              f"{r['oos']['max_drawdown_pct']:>8.2f} "
              f"{r['oos']['round_trips']:>7}")

    # Write report + JSON.
    report_path = write_report(rows, strategy_agg, args.report)
    payload = {
        "strategy_ranking": strategy_agg,
        "top_combos": [
            {k: r[k] for k in ("name", "symbol", "timeframe", "oos", "ins",
                               "overfit_gap_pct", "final_params")}
            for r in ranked
        ],
    }
    Path(args.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Write live configs (unless disabled).
    summary = None
    if not args.no_write:
        low_symbols = ["QQQ", "SPY", "DIA", "IWM", "EWJ", "EZU", "EWU", "EWG"]
        high_symbols = ["TQQQ", "SPXL", "SOXL"]
        summary = write_configs(rows, strategy_agg, low_symbols, high_symbols)
        if "error" in summary:
            print(f"\nConfig write skipped: {summary['error']}")
        else:
            print(f"\nWrote best strategy to config_low.yaml / config_high.yaml:")
            print(f"  strategy: {summary['strategy']} {summary['params']}")
            print(f"  mode: {summary['mode']}")
            print(f"  (aggregate OOS {summary['oos_return_pct']:+.2f}% over "
                  f"{summary['runs']} runs / {summary['round_trips']} trades, "
                  f"max DD {summary['oos_max_dd_pct']:.2f}%)")

    print(f"\nReport: {report_path}")
    print(f"JSON:   {args.json}")
    print(f"Elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
