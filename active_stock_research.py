"""Long-only active-stock ORB research; data client only, no order API.

Fixed present-day universe is explicitly selection-biased, not a replication
of a point-in-time all-stock study. No automatic strategy promotion.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time

import pandas as pd
from intraday_research import sessions, metrics

SYMBOLS = ("AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOG", "TSLA", "AMD",
           "JPM", "BAC", "XOM", "CVX", "WMT", "DIS", "NFLX", "INTC",
           "UBER", "PLTR", "AVGO", "MU")
RULES = dict(universe=list(SYMBOLS), opening_minutes=5, volume_history=20,
    relative_volume_min=2.0, select_top=5, minimum_price=5,
    minimum_prior_daily_dollars=20000000, risk_per_trade=.001,
    total_initial_risk=.005, max_symbol_exposure=.20, max_total_exposure=.75,
    daily_entry_cutoff=.005, daily_exit_trigger=.01, permanent_drawdown=.10,
    entry_deadline_minute=90, exit_minute=385, max_attempts_per_symbol=1,
    shorting=False, take_profit=False)


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_symbol(symbol, directory, start, end):
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import DataFeed, Adjustment
    client = StockHistoricalDataClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_API_SECRET"])
    frames = []
    edges = pd.date_range(start, end, freq="90D", tz="UTC").tolist()
    if edges[-1] != pd.Timestamp(end, tz="UTC"):
        edges.append(pd.Timestamp(end, tz="UTC"))
    for left, right in zip(edges, edges[1:]):
        request = StockBarsRequest(symbol_or_symbols=[symbol], timeframe=TimeFrame.Minute,
            start=left.to_pydatetime(), end=right.to_pydatetime(), feed=DataFeed.SIP,
            adjustment=Adjustment.RAW)
        for attempt in range(3):
            try:
                frame = client.get_stock_bars(request).df.reset_index()
                break
            except Exception:
                if attempt == 2:
                    raise RuntimeError(f"Data download failed for {symbol}; no result claimed") from None
                time.sleep(2**attempt)
        frames.append(frame)
    data = pd.concat(frames).drop_duplicates(["symbol", "timestamp"])
    path = directory / f"{symbol}.csv"
    data.to_csv(path,index=False)
    path.with_suffix(".metadata.json").write_text(json.dumps(dict(symbol=symbol,
        start=start,end=end,feed="sip",adjustment="raw",sha256=hash_file(path),rows=len(data)),indent=2))
    print(f"Downloaded {symbol}: {len(data)} minute bars",flush=True)


def load_universe(directory):
    by_date, exclusions, histories, hashes = {}, {}, {}, {}
    for symbol in SYMBOLS:
        path = directory / f"{symbol}.csv"
        data = pd.read_csv(path)
        if set(data.symbol) != {symbol}:
            raise ValueError(f"Wrong symbol in {path.name}")
        # Reuse strict validation without mutating the frozen QQQ rules.
        validated = data.assign(symbol="QQQ")
        valid, excluded = sessions(validated)
        exclusions[symbol] = excluded
        hashes[symbol] = hash_file(path)
        history = []
        for date, frame in valid:
            opening = frame.iloc[:5]
            opening_volume = float(opening.volume.sum())
            prior_volume = sum(x[0] for x in history[-20:])/20 if len(history)>=20 else None
            prior_dollars = sum(x[1] for x in history[-20:])/20 if len(history)>=20 else 0
            ratio = opening_volume/prior_volume if prior_volume else 0
            # Only the first five completed minutes and prior sessions select stocks.
            info = dict(relative_volume=ratio, prior_dollars=prior_dollars,
                opening_high=float(opening.high.max()), stop=float(opening.low.min()),
                opening_price=float(opening.iloc[-1].close))
            array = frame[["open","high","low","close","volume"]].to_numpy()
            by_date.setdefault(date,{})[symbol] = (array, info)
            history.append((opening_volume,float((frame.close*frame.volume).sum())))
        histories[symbol] = len(valid)
    return by_date, dict(excluded=exclusions, complete_sessions=histories, hashes=hashes)


def rank(stocks):
    candidates = [(symbol, info["relative_volume"]) for symbol,(_,info) in stocks.items()
        if info["relative_volume"] >= RULES["relative_volume_min"]
        and info["prior_dollars"] >= RULES["minimum_prior_daily_dollars"]
        and info["opening_price"] >= RULES["minimum_price"]]
    return [symbol for symbol,_ in sorted(candidates,key=lambda x:(-x[1],x[0]))[:RULES["select_top"]]]


def replay(by_date, costs_bps=10, delay=1, initial=100000):
    cash, peak, permanent = float(initial),float(initial),False
    daily, trades, signals = [],[],[]
    cost = costs_bps/10000
    for date, stocks in sorted(by_date.items()):
        starting = cash
        selected = rank(stocks) if not permanent else []
        positions, pending, attempted = {},{},set()
        halted, exit_pending, worst, used_risk, guard_events = permanent,False,0.,0.,0
        daily_exit_latched = False

        def close(symbol, minute, price, reason):
            nonlocal cash
            position = positions.pop(symbol)
            net = price*(1-cost)
            cash += position["quantity"]*net
            trades.append(dict(date=date,symbol=symbol,entry_minute=position["minute"],
                exit_minute=minute,quantity=position["quantity"],entry=position["entry"],
                exit_net=net,pnl=position["quantity"]*(net-position["entry"]),reason=reason))

        for minute in range(5,390):
            if exit_pending or minute >= RULES["exit_minute"]:
                for symbol in list(positions):
                    close(symbol,minute,float(stocks[symbol][0][minute,0]),
                          "account_guard" if exit_pending else "end_of_day")
                pending.clear()
                halted = True
                exit_pending = False
            for symbol in list(positions):
                bar = stocks[symbol][0][minute]
                if bar[2] <= positions[symbol]["stop"]:
                    close(symbol,minute,min(float(bar[0]),positions[symbol]["stop"]),"stop")
            # Full simulated fills are assumptions, not evidence of real execution.
            for symbol in list(pending):
                order = pending[symbol]
                if order["due"] != minute:
                    continue
                del pending[symbol]
                bar = stocks[symbol][0][minute]
                entry = float(bar[0])*(1+cost)
                exposure = sum(p["quantity"]*stocks[s][0][minute,0] for s,p in positions.items())
                if halted or entry>order["limit"] or entry<=order["stop"] or order["quantity"]*entry>cash or exposure+order["quantity"]*entry>starting*RULES["max_total_exposure"]:
                    signals.append(dict(date=date,symbol=symbol,minute=minute,event="fill_rejected"))
                    continue
                cash -= order["quantity"]*entry
                positions[symbol] = dict(quantity=order["quantity"],entry=entry,
                    stop=order["stop"],minute=minute)
                if bar[2] <= order["stop"]:
                    close(symbol,minute,min(float(bar[0]),order["stop"]),"entry_bar_stop")
            marked = cash + sum(p["quantity"]*stocks[s][0][minute,3]*(1-cost) for s,p in positions.items())
            # Simultaneous lows are a conservative stress bound, not an observed
            # tick-by-tick account path. Guard liquidates next minute (latency).
            adverse = cash + sum(p["quantity"]*stocks[s][0][minute,2]*(1-cost) for s,p in positions.items())
            worst = min(worst,(adverse/starting-1)*100)
            peak = max(peak,marked)
            if adverse <= peak*(1-RULES["permanent_drawdown"]) or adverse <= initial*(1-RULES["permanent_drawdown"]):
                permanent = halted = True
                exit_pending = bool(positions)
            if adverse <= starting*(1-RULES["daily_exit_trigger"]) and not daily_exit_latched:
                daily_exit_latched = True
                guard_events += 1
                exit_pending = bool(positions)
                halted = True
            if adverse <= starting*(1-RULES["daily_entry_cutoff"]):
                halted = True
            if halted:
                pending.clear()
                continue
            if minute+delay >= RULES["entry_deadline_minute"]:
                continue
            for symbol in selected:
                if symbol in attempted:
                    continue
                array, info = stocks[symbol]
                if array[minute,3] <= info["opening_high"]:
                    continue
                attempted.add(symbol)
                limit = float(array[minute,3])*(1+cost)
                stop = info["stop"]
                unit_risk = limit-stop*(1-cost)
                exposure = sum(p["quantity"]*stocks[s][0][minute,3] for s,p in positions.items())
                reserved = sum(p["quantity"]*p["limit"] for p in pending.values())
                budget = min(starting*RULES["risk_per_trade"],starting*RULES["total_initial_risk"]-used_risk)
                available = min(cash-reserved, starting*RULES["max_total_exposure"]-exposure-reserved,
                                starting*RULES["max_symbol_exposure"])
                qty = max(0,min(math.floor(budget/unit_risk),math.floor(available/limit))) if unit_risk>0 else 0
                signals.append(dict(date=date,symbol=symbol,minute=minute,event="signal",
                    relative_volume=info["relative_volume"],quantity=qty,limit=limit,stop=stop))
                if qty:
                    pending[symbol]=dict(due=minute+delay,quantity=qty,limit=limit,stop=stop)
                    used_risk += qty*unit_risk
        assert not positions and not pending and cash >= 0
        daily.append(dict(date=date,equity=cash,pnl=cash-starting,return_pct=(cash/starting-1)*100,
            worst_intraday_pct=worst,selected=",".join(selected),entry_halted=halted,
            permanent_halt=permanent,guard_events=guard_events))
    return daily,trades,signals


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download",action="store_true")
    parser.add_argument("--data",type=Path,default=Path("cache/active_stocks"))
    parser.add_argument("--output",type=Path,default=Path("research_runs/active_stocks"))
    parser.add_argument("--start",default="2025-01-01")
    parser.add_argument("--end",default="2026-10-02")
    parser.add_argument("--dashboard-summary",type=Path)
    parser.add_argument("--freeze-forward",action="store_true",
                        help="Freeze a prospective, simulated-only test; excludes today's session")
    parser.add_argument("--forward",action="store_true",
                        help="Replay only dates strictly after the frozen date; refresh data with --download")
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    frozen = args.output/"frozen_rules.json"
    if frozen.exists() and json.loads(frozen.read_text())["rules"] != RULES:
        raise ValueError("Rules changed; use a separate experiment output directory")
    if not frozen.exists():
        frozen.write_text(json.dumps(dict(rules=RULES,created_utc=datetime.now(timezone.utc).isoformat(),
            source_hash=hash_file(Path(__file__)),historical_research_only=True),indent=2))
    forward_path=args.output/"forward_manifest.json"
    if args.freeze_forward and not forward_path.exists():
        now=pd.Timestamp.now(tz="America/New_York")
        forward_path.write_text(json.dumps(dict(rules=RULES,source_hash=hash_file(Path(__file__)),
            excluded_through=str(now.date()),created_utc=datetime.now(timezone.utc).isoformat(),
            initial_virtual_usd=100000,broker_orders_enabled=False,
            mode="After-close replay of future completed sessions; not a live tick execution test"),indent=2))
    if args.forward:
        manifest=json.loads(forward_path.read_text())
        if manifest["rules"] != RULES or manifest["source_hash"] != hash_file(Path(__file__)):
            raise ValueError("Frozen forward test code/rules changed; create a new separately identified test")
    if args.download:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent/".env")
        args.data.mkdir(parents=True,exist_ok=True)
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda s: fetch_symbol(s,args.data,args.start,args.end),SYMBOLS))
    data,quality=load_universe(args.data)
    if args.forward:
        future={date:stocks for date,stocks in data.items() if date>manifest["excluded_through"]}
        daily,trades,signals=replay(future,initial=manifest["initial_virtual_usd"])
        forward=dict(manifest=manifest,sessions=len(daily),
            metrics=metrics(daily,manifest["initial_virtual_usd"]),
            daily=daily,trades=trades,signals=signals,
            status="awaiting_new_completed_sessions" if not daily else "simulated_forward_observations",
            updated_utc=datetime.now(timezone.utc).isoformat(),input_hashes=quality["hashes"])
        for suffix,rows in [("daily",daily),("trades",trades),("signals",signals)]:
            pd.DataFrame(rows).to_csv(args.output/f"forward_{suffix}.csv",index=False)
        (args.output/"forward_results.json").write_text(json.dumps(forward,indent=2))
        print(json.dumps({k:v for k,v in forward.items() if k!="input_hashes"},indent=2))
        return
    if len(data)<100:
        raise ValueError("Insufficient sessions for historical research")
    report=dict(rules=RULES,quality=quality,source_hash=hash_file(Path(__file__)),
        generated_utc=datetime.now(timezone.utc).isoformat(),runs={},cash_return_pct=0,
        untouched_holdout_claim=False,real_trading_approved=False,
        limitations=["20 current stocks: selection/survivorship bias; not all-stock paper replication",
            "Incomplete and early-close sessions excluded; data availability affects stock ranking",
            "No shorting, news classifier or point-in-time universe",
            "OHLC fill assumptions omit quotes, partial fills, queue position, taxes and FX",
            "Intraminute low guard is a conservative bound, not actual synchronized prices",
            "No automatic deployment or brokerage orders; prospective test still required"])
    for name,cost,delay in [("base",10,1),("higher_cost",25,1),("delayed",10,2)]:
        daily,trades,signals=replay(data,cost,delay)
        cut=int(len(daily)*.8)
        initial=daily[cut-1]["equity"]
        report["runs"][name]=dict(full=metrics(daily,100000),
            final_period=metrics(daily[cut:],initial),final_start=daily[cut]["date"],
            trades=len(trades),final_trades=sum(t["date"]>=daily[cut]["date"] for t in trades),
            costs_bps=cost,delay_minutes=delay,permanent_halt=daily[-1]["permanent_halt"])
        for suffix,rows in [("daily",daily),("trades",trades),("signals",signals)]:
            pd.DataFrame(rows).to_csv(args.output/f"{name}_{suffix}.csv",index=False)
    stress_pass=all(run["full"]["total_return_pct"]>0 and run["final_period"]["total_return_pct"]>0
                    and not run["permanent_halt"] for run in report["runs"].values())
    report["historical_screen_passed"]=stress_pass
    report["verdict"]=("Historical screening only; prospective evidence required. Not approved for deployment."
        if stress_pass else "Rejected for strategy promotion: fails profitability/cost screening. Not a daily-income solution.")
    (args.output/"results.json").write_text(json.dumps(report,indent=2))
    if args.dashboard_summary:
        summary={k:v for k,v in report.items() if k!="quality"}
        summary["data_range"]=[min(data),max(data)]
        summary["quality_summary"]={s:dict(complete_sessions=quality["complete_sessions"][s],
            excluded_sessions=len(quality["excluded"][s])) for s in SYMBOLS}
        args.dashboard_summary.write_text(json.dumps(summary,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!="quality"},indent=2))


if __name__=="__main__":
    main()
