"""Past-only quote features and a bounded historical SIP collector, no orders.

Displayed best bid/ask sizes are NOT the full order book or executed order flow.
Ten-second samples are exploratory. They do not establish minute/hour alpha.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

from active_stock_research import load_universe
from regime_predictive_research import extended_rows
from quote_cost_audit import fetch_pages,weighted_quantile
from prospective_outcome_audit import save_once_or_identical

SYMBOLS=['AAPL','MSFT','NVDA','TSLA','JPM','DIS']
FEATURES=['time_weighted_imbalance','imbalance_std','mean_full_spread_bps',
    'p95_full_spread_bps','weighted_mid_pressure_bps','last_imbalance',
    'observed_mid_return_bps','observed_mid_volatility_bps','normalized_quote_flow_per_second']
PROTOCOL=dict(symbols=SYMBOLS,maximum_dates=180,sampling='evenly spaced eligible historical dates',
    cutoff_ny='10:00:00',window_seconds=10,seed_seconds=2,max_quote_age_seconds=2,
    minimum_fresh_coverage_pct=90,feed='sip',information_delay_minutes=15,
    request_spacing_seconds=.4,orders=False,independent_validation_pass=False)


def quote_features(quotes,start,end,max_age=2,minimum_coverage=90):
    lo,hi=pd.Timestamp(start).value,pd.Timestamp(end).value
    if hi<=lo or max_age<=0: raise ValueError('Invalid quote feature window')
    points={}
    for quote in quotes:
        stamp=pd.Timestamp(quote['t']).value
        if not lo-int(max_age*1e9)<=stamp<hi: continue  # no future information
        state=tuple(float(quote.get(key,0)) for key in ['bp','ap','bs','as'])
        if stamp in points and points[stamp]!=state: points[stamp]=None
        else: points[stamp]=state
    timeline=sorted(points.items());values=[];weights=[];mids=[];flow=0.;returns=[]
    previous=None
    for index,(stamp,state) in enumerate(timeline):
        valid=state is not None and np.isfinite(state).all() and state[0]>0 and state[1]>=state[0] and min(state[2:])>0
        if not valid: previous=None;continue
        bid,ask,bs,az=state;mid=(bid+ask)/2;imbalance=(bs-az)/(bs+az)
        following=timeline[index+1][0] if index+1<len(timeline) else hi
        left=max(lo,stamp);right=min(hi,following,stamp+int(max_age*1e9))
        duration=(right-left)/1e9
        if duration>0:
            weighted_mid=(ask*bs+bid*az)/(bs+az)
            values.append([imbalance,(ask-bid)/mid*1e4,(weighted_mid-mid)/mid*1e4,bs+az])
            weights.append(duration);mids.append(mid)
        if previous is not None and stamp>=lo and stamp-previous[0]<=int(max_age*1e9):
            _,(pb,pa,pbs,paz)=previous
            flow+=(bs if bid>=pb else 0)-(pbs if bid<=pb else 0)-(az if ask<=pa else 0)+(paz if ask>=pa else 0)
            returns.append(np.log(mid/((pb+pa)/2)))
        previous=(stamp,state)
    coverage=sum(weights)/((hi-lo)/1e9)*100
    terminal=bool(previous and timeline and previous[0]==timeline[-1][0] and hi-previous[0]<=int(max_age*1e9))
    result=dict(fresh_coverage_pct=coverage,terminal_quote_fresh=terminal,
        unique_past_timestamps=len(timeline),status='usable' if coverage>=minimum_coverage and terminal and weights else 'insufficient_quote_coverage',
        features=None)
    if result['status']=='usable':
        v=np.array(values);w=np.array(weights);mean=np.average(v,axis=0,weights=w)
        result['features']=[float(mean[0]),float(np.sqrt(np.average((v[:,0]-mean[0])**2,weights=w))),
            float(mean[1]),weighted_quantile(v[:,1],w,.95),float(mean[2]),float(v[-1,0]),
            float((mids[-1]/mids[0]-1)*1e4),float(np.sqrt(np.sum(np.array(returns)**2))*1e4),
            float(flow/mean[3]/((hi-lo)/1e9))]
        if not np.isfinite(result['features']).all(): raise ValueError('Nonfinite quote features')
    return result


def bounds(date):
    cutoff=pd.Timestamp(date+' 10:00:00',tz='America/New_York').tz_convert('UTC')
    start=cutoff-pd.Timedelta(seconds=10)
    return start,cutoff


class RateGate:
    def __init__(self): self.lock=threading.Lock();self.last=0.
    def wait(self):
        with self.lock:
            pause=max(0,.4-(time.monotonic()-self.last))
            if pause: time.sleep(pause)
            self.last=time.monotonic()


def collect_window(symbol,date,cache,rate):
    start,end=bounds(date)
    identity=dict(symbol=symbol,date=date,feed='sip',start=start.isoformat(),cutoff=end.isoformat(),seed_seconds=2)
    path=cache/f'{symbol}_{date}.json'
    if path.exists():
        payload=json.loads(path.read_text())
        if payload.get('identity')!=identity or not payload.get('pagination_complete'):
            raise ValueError('Cached quote identity/completeness mismatch')
    else:
        headers={'APCA-API-KEY-ID':os.environ['ALPACA_API_KEY'],'APCA-API-SECRET-KEY':os.environ['ALPACA_API_SECRET']}
        def get(params):
            rate.wait()
            response=requests.get('https://data.alpaca.markets/v2/stocks/quotes',headers=headers,params=params,timeout=30)
            if response.status_code!=200: raise RuntimeError(f'Market-data HTTP {response.status_code}')
            return response.json()
        # API end is inclusive: omit the exact feature cutoff by one nanosecond.
        payload=fetch_pages(get,symbol,(start-pd.Timedelta(seconds=2)).isoformat(),
            (end-pd.Timedelta(nanoseconds=1)).isoformat(),maximum=20)
        payload.update(identity=identity,retrieved_utc=datetime.now(timezone.utc).isoformat())
        save_once_or_identical(path,json.dumps(payload,allow_nan=False).encode())
    return dict(**identity,cache_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        pages=payload['pages'],raw_quotes=len(payload['quotes']),
        **quote_features(payload['quotes'],start,end))


def collect(data,output):
    output.mkdir(parents=True,exist_ok=True);cache=output/'quotes';cache.mkdir(exist_ok=True)
    by_date,evidence=load_universe(data);rows=extended_rows(by_date)
    available={date:{r['symbol'] for r in rows if r['date']==date} for date in sorted(by_date)}
    eligible=[date for date,symbols in available.items() if set(SYMBOLS)<=symbols]
    if not eligible: raise ValueError('No historical eligible dates')
    chosen=[eligible[i] for i in np.linspace(0,len(eligible)-1,min(180,len(eligible)),dtype=int)]
    plan=dict(protocol=PROTOCOL,dates=chosen,bar_cache_sha256=evidence['hashes'])
    save_once_or_identical(output/'request_plan.json',json.dumps(plan,indent=2).encode())
    load_dotenv();rate=RateGate()
    report=dict(status='historical_quote_exploration_only',plan=plan,feature_names=FEATURES,windows=[],orders=False)
    def work(task):
        try: return collect_window(*task,cache,rate)
        except Exception as error: return dict(symbol=task[0],date=task[1],status='quote_fetch_failed',error_type=type(error).__name__)
    tasks=[(symbol,date) for date in chosen for symbol in SYMBOLS]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for index,result in enumerate(pool.map(work,tasks),1):
            report['windows'].append(result)
            (output/'collection_status.json').write_text(json.dumps(report,indent=2,allow_nan=False))
            if index%12==0 or index==len(tasks):
                print(json.dumps(dict(completed=index,total=len(tasks),usable=sum(w['status']=='usable' for w in report['windows']),
                    failed=sum(w['status']=='quote_fetch_failed' for w in report['windows']))),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/quote_microstructure'))
    args=parser.parse_args();collect(args.data,args.output)
