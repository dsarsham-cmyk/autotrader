"""Read-only SIP quote diagnostic. Spread is NOT total executable cost.

Fixed pilot windows are not a representative all-market execution study.
No broker/order module, no subscription changes, no strategy promotion.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import requests
from dotenv import load_dotenv
import pandas as pd

SYMBOLS=['AAPL','NVDA','TSLA','JPM','DIS','QQQ']
DATES=['2025-03-03','2025-09-02','2026-04-01','2026-09-23']
TIMES=['09:45','10:00','15:55']


def fetch_pages(get, symbol, start, end, maximum=100):
    token=None
    seen=set()
    quotes=[]
    for page in range(maximum):
        params=dict(symbols=symbol,start=start,end=end,feed='sip',limit=10000,sort='asc')
        if token: params['page_token']=token
        response=get(params)
        quotes.extend(response.get('quotes',{}).get(symbol,[]))
        token=response.get('next_page_token')
        if not token:
            return dict(quotes=quotes,pages=page+1,pagination_complete=True)
        if token in seen:
            raise ValueError('Repeated pagination token; incomplete evidence')
        seen.add(token)
    raise ValueError('Pagination ceiling reached; incomplete evidence')


def weighted_quantile(values, weights, probability):
    order=np.argsort(values)
    v=np.asarray(values)[order]
    w=np.asarray(weights)[order]
    return float(v[np.searchsorted(np.cumsum(w),probability*sum(w),side='left')])


def summarize(quotes,start,end,max_age_seconds=2):
    lo,hi=pd.Timestamp(start).value,pd.Timestamp(end).value
    if hi<=lo: raise ValueError('Empty assessment window')
    # Keep invalid quotes in timeline: they must interrupt valid coverage.
    points=sorted({pd.Timestamp(q['t']).value:(float(q.get('bp',0)),float(q.get('ap',0)),
                 float(q.get('bs',0)),float(q.get('as',0))) for q in quotes}.items())
    values,weights=[],[]
    invalid=0
    for i,(stamp,(bid,ask,bs,az)) in enumerate(points):
        valid=np.isfinite([bid,ask,bs,az]).all() and bid>0 and ask>=bid and bs>0 and az>0
        if not valid:
            invalid+=1
            continue
        following=points[i+1][0] if i+1<len(points) else hi
        right=min(hi,following,stamp+int(max_age_seconds*1e9))
        left=max(lo,stamp)
        duration=(right-left)/1e9
        if duration<=0: continue
        values.append((ask-bid)/((ask+bid)/2)*10000)
        weights.append(duration)
    duration=(hi-lo)/1e9
    return dict(raw_quotes=len(quotes),unique_timestamps=len(points),invalid_quotes=invalid,
        observed_first=pd.Timestamp(points[0][0],tz='UTC').isoformat() if points else None,
        observed_last=pd.Timestamp(points[-1][0],tz='UTC').isoformat() if points else None,
        fresh_coverage_pct=sum(weights)/duration*100,
        time_weighted_full_spread_median_bps=weighted_quantile(values,weights,.5) if weights else None,
        time_weighted_full_spread_p95_bps=weighted_quantile(values,weights,.95) if weights else None,
        max_quote_age_seconds=max_age_seconds)


def window(symbol,date,clock,cache):
    start=datetime.fromisoformat(date+'T'+clock).replace(tzinfo=ZoneInfo('America/New_York'))
    end=start+timedelta(seconds=30)
    stamp=lambda value:value.astimezone(ZoneInfo('UTC')).isoformat()
    begin,finish=stamp(start),stamp(end)
    path=cache/f"{symbol}_{date}_{clock.replace(':','')}.json"
    if path.exists():
        payload=json.loads(path.read_text())
        if not payload.get('pagination_complete'):
            raise ValueError('Incomplete cached quote sample')
    else:
        headers={'APCA-API-KEY-ID':os.environ['ALPACA_API_KEY'],
                 'APCA-API-SECRET-KEY':os.environ['ALPACA_API_SECRET']}
        def get(params):
            response=requests.get('https://data.alpaca.markets/v2/stocks/quotes',
                headers=headers,params=params,timeout=30)
            if response.status_code!=200:
                raise RuntimeError(f'Market-data HTTP {response.status_code}; no result claimed')
            return response.json()
        payload=fetch_pages(get,symbol,stamp(start-timedelta(seconds=10)),finish)
        payload.update(symbol=symbol,start=begin,end=finish,feed='sip')
        path.write_text(json.dumps(payload,allow_nan=False))
    if (payload['symbol'],payload['start'],payload['end'],payload['feed'])!=(symbol,begin,finish,'sip'):
        raise ValueError('Cache request identity mismatch')
    return dict(symbol=symbol,date=date,time_ny=clock,start=begin,end=finish,
        pages=payload['pages'],pagination_complete=True,
        cache_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        **summarize(payload['quotes'],begin,finish))


def run(output):
    cache=output/'quotes'
    cache.mkdir(parents=True,exist_ok=True)
    load_dotenv()
    report=dict(status='diagnostic_only',cost_assumptions_changed=False,
        protocol=dict(symbols=SYMBOLS,dates=DATES,times_ny=TIMES,seconds_per_window=30,
        feed='sip',weighting='elapsed time, not number of quote updates',max_quote_age_seconds=2),
        limitations=['Handpicked limited pilot, not representative all-market costs',
            'Full quoted spread is not market impact, latency, commissions, or fees',
            'Half spread assumes midpoint benchmark and immediately executable sizes',
            'No cost reduction or model promotion authorized by this diagnostic'],windows=[])
    tasks=[(s,d,t) for s in SYMBOLS for d in DATES for t in TIMES]
    def work(task):
        try: return window(*task,cache)
        except Exception as error:
            return dict(symbol=task[0],date=task[1],time_ny=task[2],
                error_type=type(error).__name__,pagination_complete=False)
    with ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(work,tasks):
            report['windows'].append(result)
            (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
            print(json.dumps({k:result[k] for k in result if k in
                {'symbol','date','time_ny','fresh_coverage_pct','error_type'}}),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('research_runs/quote_cost_audit'))
    run(parser.parse_args().output)
