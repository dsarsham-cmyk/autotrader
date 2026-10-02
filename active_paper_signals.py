"""Real paper-execution variant: IEX opening volume and completed minutes.

Different feed/entry mechanics from the SIP historical experiment. This module
only supplies signals; the existing single account controller owns all orders.
"""
from datetime import datetime, timedelta, timezone
import time

import pandas as pd

from paper_safety import NY


def opening_features(frame, dates):
    frame=frame.copy()
    frame["timestamp"]=pd.to_datetime(frame["timestamp"],utc=True)
    frame=frame.set_index("timestamp").sort_index().tz_convert(NY)
    regular=frame.between_time("09:30","15:59")
    totals={}
    for date,bars in regular.groupby(regular.index.strftime("%Y-%m-%d")):
        if len(bars)<100:
            continue  # thin/incomplete prior evidence cannot permit an entry
        opening=bars.between_time("09:30","09:34")
        if opening.empty:
            continue
        totals[date]=(float(opening.volume.sum()),float((bars.close*bars.volume).sum()))
    if len(dates)!=20 or any(date not in totals for date in dates):
        return None
    return dict(volume=sum(totals[d][0] for d in dates)/20,
                dollars=sum(totals[d][1] for d in dates)/20)


def opening_signals(data, history, now):
    """Rank from completed opening bars only; no current-day future data."""
    local=now.astimezone(NY)
    day=local.date().isoformat()
    if (local.hour,local.minute)<(9,35) or (local.hour,local.minute)>=(11,0):
        return {}
    candidates=[]
    for symbol,frame in data.items():
        frame=frame.copy()
        frame["timestamp"]=pd.to_datetime(frame["timestamp"],utc=True)
        frame=frame.set_index("timestamp").sort_index().tz_convert(NY)
        # A minute stamped 09:35 is usable only at/after 09:36.
        frame=frame[(frame.index+pd.Timedelta(minutes=1)<=now) &
                    (frame.index.strftime("%Y-%m-%d")==day)]
        frame=frame.between_time("09:30","10:59")
        opening=frame.between_time("09:30","09:34")
        previous=history.get(symbol)
        if opening.empty or frame.empty or not previous or previous["volume"]<=0 or previous["dollars"]<20000000:
            continue
        ratio=float(opening.volume.sum())/previous["volume"]
        if ratio<2 or float(opening.iloc[-1].close)<5:
            continue
        candidates.append((symbol,ratio,frame,opening))
    result={}
    for symbol,ratio,frame,opening in sorted(candidates,key=lambda v:(-v[1],v[0]))[:5]:
        latest=frame.iloc[-1]
        age=(now-frame.index[-1].to_pydatetime()-timedelta(minutes=1)).total_seconds()
        high,low=float(opening.high.max()),float(opening.low.min())
        if 0<=age<=120 and float(latest.close)>high and low>0 and high>low:
            result[symbol]=dict(signal="buy",atr=high-low,stop_price=low,
                limit_cap=round(float(latest.close)*1.001+.005,2),
                at=time.time(),market_day=day,deadline=f"{day}T11:00:00{local.strftime('%z')}",
                relative_volume=ratio,feed="iex",variant="paper execution, not SIP research")
    return result


def collect(api,config,signals,health,key,secret):
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import DataFeed,Adjustment
    client=StockHistoricalDataClient(key,secret)
    symbols=config["stock"]["symbols"]
    cached_day=None
    history_dates=()
    history={}
    while True:
        try:
            clock=api.call("GET","/v2/clock")
            now=datetime.now(timezone.utc)
            local=now.astimezone(NY)
            for symbol in symbols:
                signals.pop(symbol,None)
            day=local.date().isoformat()
            start=local.replace(hour=9,minute=30,second=0,microsecond=0)
            if cached_day!=day:
                calendar=api.call("GET","/v2/calendar",params={"start":str(local.date()-timedelta(days=60)),"end":day})
                dates=[entry["date"] for entry in calendar if entry["date"]<day][-20:]
                if tuple(dates)!=history_dates:
                    request=StockBarsRequest(symbol_or_symbols=symbols,timeframe=TimeFrame.Minute,
                        start=start-timedelta(days=60),end=start-timedelta(microseconds=1),
                        feed=DataFeed.IEX,adjustment=Adjustment.RAW)
                    bars=client.get_stock_bars(request).df.reset_index()
                    history={symbol:opening_features(frame,dates) for symbol,frame in bars.groupby("symbol")}
                    history_dates=tuple(dates)
                cached_day=day
            if not clock["is_open"] or (local.hour,local.minute)<(9,35) or (local.hour,local.minute)>=(11,0):
                health.update(status="waiting for next eligible market opening",feed="iex",
                    updated_at=now.isoformat(),history_symbols=sum(bool(v) for v in history.values()),errors=[])
                time.sleep(30)
                continue
            request=StockBarsRequest(symbol_or_symbols=symbols,timeframe=TimeFrame.Minute,
                start=start,end=now-timedelta(seconds=1),feed=DataFeed.IEX,adjustment=Adjustment.RAW)
            bars=client.get_stock_bars(request).df.reset_index()
            fresh=opening_signals({s:f for s,f in bars.groupby("symbol")},history,datetime.now(timezone.utc))
            signals.update(fresh)
            health.update(status="collecting completed-minute opening breakouts",feed="iex",
                updated_at=datetime.now(timezone.utc).isoformat(),eligible_signals=list(fresh),
                history_symbols=sum(bool(v) for v in history.values()),errors=[])
        except Exception as error:
            for symbol in symbols:
                signals.pop(symbol,None)
            health.update(status="data unavailable: new experiment entries disabled",
                updated_at=datetime.now(timezone.utc).isoformat(),errors=[type(error).__name__])
        time.sleep(30)
