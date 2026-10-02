"""Isolated, read-only-data ORB experiment. Never imports a trading client.

One fixed QQQ hypothesis, not a reproduction of the stocks-in-play paper.
Download requires existing Alpaca data access; no subscription is purchased.
Generated files are research evidence, never production configuration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path

import pandas as pd

RULES = dict(symbol="QQQ", opening_minutes=5, volume_ratio=1.5,
             volume_history=20, risk_per_trade=0.002, max_exposure=1.0,
             daily_entry_cutoff=0.005, daily_exit_trigger=0.01,
             entry_deadline="11:00", exit_time="15:55", trades_per_day=1,
             take_profit="none: allow trend to run until stop or session exit")


def download(path, start, end, feed):
    from dotenv import load_dotenv
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import DataFeed, Adjustment
    load_dotenv(Path(__file__).parent / ".env")
    client = StockHistoricalDataClient(os.environ["ALPACA_API_KEY"],
                                      os.environ["ALPACA_API_SECRET"])
    frames = []
    # Bounded chunks avoid one enormous request; SDK handles pagination.
    boundaries = pd.date_range(start, end, freq="30D", tz="UTC").tolist()
    if not boundaries or boundaries[-1] != pd.Timestamp(end, tz="UTC"):
        boundaries.append(pd.Timestamp(end, tz="UTC"))
    for left, right in zip(boundaries, boundaries[1:]):
        request = StockBarsRequest(symbol_or_symbols=[RULES["symbol"]],
            timeframe=TimeFrame.Minute, start=left.to_pydatetime(),
            end=right.to_pydatetime(), feed=DataFeed(feed), adjustment=Adjustment.RAW)
        frame = client.get_stock_bars(request).df
        if not frame.empty:
            frames.append(frame.reset_index())
        print(f"Data chunk {left.date()} to {right.date()}: {len(frame)} bars", flush=True)
    if not frames:
        raise ValueError("No minute data returned; no result can be claimed")
    data = pd.concat(frames).drop_duplicates(["symbol", "timestamp"])
    path.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(path, index=False)
    path.with_suffix(".metadata.json").write_text(json.dumps(
        dict(feed=feed, start=start, end=end, symbol=RULES["symbol"],
             rows=len(data), sha256=hashlib.sha256(path.read_bytes()).hexdigest()), indent=2))


def sessions(data):
    data = data.copy()
    if set(data["symbol"]) != {RULES["symbol"]}:
        raise ValueError("Frozen hypothesis only supports QQQ")
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    if data["timestamp"].duplicated().any():
        raise ValueError("Duplicate timestamps")
    data = data.set_index("timestamp").sort_index().tz_convert("America/New_York")
    numeric = data[["open", "high", "low", "close", "volume"]]
    if numeric.isna().any().any() or not all(math.isfinite(v) for v in numeric.to_numpy().flat):
        raise ValueError("Non-finite bars")
    if ((data.low > data[["open", "close"]].min(axis=1)) |
        (data.high < data[["open", "close"]].max(axis=1)) |
        (data.low <= 0) | (data.volume < 0)).any():
        raise ValueError("Invalid OHLCV")
    regular = data.between_time("09:30", "15:59")
    valid, excluded = [], []
    for day, frame in regular.groupby(regular.index.date):
        expected = pd.date_range(str(day)+" 09:30", periods=390, freq="min",
                                 tz="America/New_York")
        if not frame.index.equals(expected):
            excluded.append(dict(date=str(day), bars=len(frame), reason="Incomplete normal session; half-days excluded too"))
            continue
        valid.append((str(day), frame))
    return valid, excluded


def exit_price(bar, stop, target):
    # Stops first if both touched; gaps use worse opening price.
    if bar.low <= stop:
        return min(float(bar.open), stop), "stop"
    if target is not None and bar.high >= target:
        return target, "target"
    return None


def simulate(days, costs_bps=10, delay=1, initial=100000):
    equity, history, ledger, daily = initial, [], [], []
    for date, bars in days:
        starting = equity
        opening = bars.iloc[:5]
        volume = float(opening.volume.sum())
        baseline = sum(history[-20:]) / 20 if len(history) >= 20 else None
        eligible = baseline is not None and volume >= RULES["volume_ratio"] * baseline
        history.append(volume)
        signal = None
        if eligible:
            # A completed minute close confirms breakout, never its earlier high.
            for i in range(5, len(bars)):
                if bars.index[i].strftime("%H:%M") >= RULES["entry_deadline"]:
                    break
                if bars.iloc[i].close > opening.high.max():
                    signal = i
                    break
        pnl, worst = 0., 0.
        if signal is not None and signal + delay < len(bars):
            entry_index = signal + delay
            entry_time = bars.index[entry_index]
            if entry_time.strftime("%H:%M") < RULES["entry_deadline"]:
                cost = costs_bps / 10000
                # Quantity/limit are fixed from the completed signal, not the
                # next opening price. Skip a gap above limit; do not assume a
                # later intrabar limit fill whose path OHLC cannot establish.
                limit = float(bars.iloc[signal].close) * (1 + cost)
                entry = float(bars.iloc[entry_index].open) * (1 + cost)
                stop = float(opening.low.min())
                sizing_risk = limit - stop
                risk = entry - stop
                quantity = min(math.floor(starting * RULES["max_exposure"] / limit),
                               math.floor(starting * RULES["risk_per_trade"] / (sizing_risk + stop * cost))) if sizing_risk > 0 and risk > 0 and entry <= limit else 0
                if quantity > 0:
                    target = None
                    # Account loss guard is checked intrabar, not just at close.
                    guard = (entry - starting * RULES["daily_exit_trigger"] / quantity) / (1-cost)
                    stop = max(stop, guard)
                    for j in range(entry_index, len(bars)):
                        bar = bars.iloc[j]
                        forced = bars.index[j].strftime("%H:%M") >= RULES["exit_time"]
                        result = (float(bar.open), "end_of_day") if forced else exit_price(bar, stop, target)
                        mark = (bar.open if forced else min(bar.low, result[0]) if result else bar.low)
                        worst = min(worst, quantity * (mark * (1-cost) - entry))
                        if result:
                            price, reason = result
                            pnl = quantity * (price * (1-cost) - entry)
                            equity += pnl
                            ledger.append(dict(date=date, signal_time=str(bars.index[signal]),
                                entry_time=str(entry_time), exit_time=str(bars.index[j]),
                                quantity=quantity, entry=entry, exit_net=price*(1-cost),
                                stop=stop, target=target, reason=reason, pnl=pnl))
                            break
        daily.append(dict(date=date, equity=equity, pnl=pnl,
                          return_pct=pnl/starting*100, worst_intraday_pct=worst/starting*100,
                          volume_eligible=eligible))
    return daily, ledger


def metrics(rows, initial):
    if not rows:
        return dict(sessions=0)
    peak, drawdown = initial, 0.
    for row in rows:
        peak = max(peak, row["equity"])
        drawdown = max(drawdown, 1-row["equity"]/peak)
    return dict(sessions=len(rows), total_return_pct=(rows[-1]["equity"]/initial-1)*100,
                max_close_drawdown_pct=drawdown*100,
                worst_day_pct=min(r["return_pct"] for r in rows),
                mean_daily_pct=sum(r["return_pct"] for r in rows)/len(rows),
                profitable_days=sum(r["pnl"]>0 for r in rows),
                days_at_least_1pct=sum(r["return_pct"]>=1 for r in rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("cache/intraday/QQQ_1m.csv"))
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--feed", choices=["sip", "iex"], default="sip")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-10-02")
    parser.add_argument("--output", type=Path, default=Path("research_runs/intraday"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.download:
        download(args.data, args.start, args.end, args.feed)
    days, excluded = sessions(pd.read_csv(args.data))
    if len(days) < 100:
        raise ValueError(f"Only {len(days)} complete sessions; minimum 100 for exploratory replay")
    cut = int(len(days)*0.8)
    report = dict(rules=RULES, sha256=hashlib.sha256(args.data.read_bytes()).hexdigest(),
        complete_sessions=len(days), excluded=excluded, final_test_start=days[cut][0],
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        data_metadata=json.loads(args.data.with_suffix(".metadata.json").read_text()) if args.data.with_suffix(".metadata.json").exists() else None,
        untouched_test_claim=False, real_trading_approved=False, costs_include="adverse fill allowance each side",
        limitations=["Single ETF hypothesis, not stocks-in-play paper replication",
            "Historical data may have been examined before; chronological split is not proof of untouched data",
            "No quotes, queue position, partial fills, taxes, FX or hosting modeled",
            "Complete-session filtering can bias results; half-days excluded",
            "No prospective shadow test launched by this script; no orders placed"], runs={})
    for name, bps, delay in [("base",10,1),("higher_cost",25,1),("delayed",10,2)]:
        daily, trades = simulate(days, bps, delay)
        # Rebase final period; cash/flat at every session boundary.
        prior = daily[cut-1]["equity"]
        report["runs"][name] = dict(full=metrics(daily,100000),
            final_period=metrics(daily[cut:],prior), trades=len(trades), costs_bps=bps, delay_minutes=delay)
        pd.DataFrame(daily).to_csv(args.output / f"{name}_daily.csv", index=False)
        pd.DataFrame(trades).to_csv(args.output / f"{name}_trades.csv", index=False)
    report["cash_benchmark_return_pct"] = 0.0
    report["verdict"] = "Rejected for promotion: insufficient trades and execution sensitivity. Not a validated daily-income strategy."
    (args.output / "results.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k != "excluded"}, indent=2))


if __name__ == "__main__":
    main()
