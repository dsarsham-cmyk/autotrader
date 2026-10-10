"""New research-only mixed-feed protocol, not substitution into a SIP model.

Context: SIP bars through 10:00, assumed available 10:15. New information: IEX
quotes through 10:15:30, assumed real-time availability, entry no earlier than
10:16. Thirty seconds for receipt/inference/anchoring remains to be verified.
Latest IEX midpoint fixes the simulated limit for BOTH matched model arms.
No orders, paid upgrades, production approval or risk relaxation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

from active_stock_research import load_universe
from regime_predictive_research import extended_rows
from quote_microstructure_research import quote_features,RateGate,SYMBOLS,FEATURES
from prospective_outcome_audit import save_once_or_identical
from quote_feature_ablation import walk,MODELS
from predictive_portfolio_research import portfolio
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic

PROTOCOL=dict(context_feed='sip',context_cutoff_ny='10:00:00',context_delay_minutes=15,
    quote_feed='iex',quote_cutoff_ny='10:15:30',entry_ny='10:16:00',
    quote_window_seconds=10,quote_seed_seconds=2,max_quote_age_seconds=2,
    minimum_quote_coverage_pct=90,maximum_terminal_full_spread_bps=20,
    signal_price='latest known IEX midpoint for both matched arms',
    entry_limit_multiplier=1.001,minimum_mid_context_ratio=.5,maximum_mid_context_ratio=1.5,
    assumed_receipt_inference_anchor_budget_seconds=30,
    receipt_latency_verified=False,orders=False,production_approved=False)


def bounds(date):
    cutoff=pd.Timestamp(date+' '+PROTOCOL['quote_cutoff_ny'],tz='America/New_York').tz_convert('UTC')
    start=cutoff-pd.Timedelta(seconds=10)
    context=pd.Timestamp(date+' '+PROTOCOL['context_cutoff_ny'],tz='America/New_York').tz_convert('UTC')
    entry=pd.Timestamp(date+' '+PROTOCOL['entry_ny'],tz='America/New_York').tz_convert('UTC')
    if context+pd.Timedelta(minutes=15)>cutoff or entry-cutoff!=pd.Timedelta(seconds=30):
        raise ValueError('Invalid mixed-feed information chronology')
    return start,cutoff,context,entry


def latest_state(quotes,end):
    cutoff=pd.Timestamp(end);eligible=[]
    for quote in quotes:
        stamp=pd.Timestamp(quote['t'])
        if stamp.tzinfo is None: raise ValueError('Aware quote timestamps required')
        if cutoff-pd.Timedelta(seconds=2)<=stamp<cutoff: eligible.append((stamp,quote))
    if not eligible: return None
    last=max(stamp for stamp,quote in eligible)
    states={tuple(float(quote.get(key,0)) for key in ['bp','ap','bs','as'])
        for stamp,quote in eligible if stamp==last}
    if len(states)!=1: return None
    bid,ask,bs,az=states.pop()
    if not np.isfinite([bid,ask,bs,az]).all() or bid<=0 or ask<bid or min(bs,az)<=0: return None
    return dict(mid=(bid+ask)/2,full_spread_bps=(ask-bid)/((ask+bid)/2)*1e4,timestamp=last.isoformat())


def fetch_batch(get,start,end,symbols):
    token=None;seen=set();pages=[];quotes={symbol:[] for symbol in symbols}
    for _ in range(20):
        params=dict(symbols=','.join(symbols),feed='iex',start=start.isoformat(),
            end=(end-pd.Timedelta(nanoseconds=1)).isoformat(),sort='asc',limit=10000)
        if token: params['page_token']=token
        page=get(params);pages.append(page)
        if set(page.get('quotes',{}))-set(symbols): raise ValueError('Unexpected quote symbol')
        for symbol,items in page.get('quotes',{}).items(): quotes[symbol].extend(items)
        token=page.get('next_page_token')
        if not token: return dict(quotes=quotes,raw_pages=pages,pages=len(pages),pagination_complete=True)
        if token in seen: raise ValueError('Repeated IEX pagination token')
        seen.add(token)
    raise ValueError('IEX pagination ceiling reached')


def collect_date(date,cache,rate):
    start,end,context,entry=bounds(date)
    identity=dict(date=date,symbols=SYMBOLS,feed='iex',start=start.isoformat(),cutoff=end.isoformat(),seed_seconds=2)
    path=cache/f'{date}.json'
    if path.exists():
        raw=json.loads(path.read_text())
        if raw.get('identity')!=identity or raw.get('pagination_complete') is not True:
            raise ValueError('Retained IEX identity/completeness mismatch')
    else:
        headers={'APCA-API-KEY-ID':os.environ['ALPACA_API_KEY'],'APCA-API-SECRET-KEY':os.environ['ALPACA_API_SECRET']}
        def get(params):
            rate.wait()
            response=requests.get('https://data.alpaca.markets/v2/stocks/quotes',headers=headers,params=params,timeout=30)
            if response.status_code!=200: raise RuntimeError(f'Research quote HTTP {response.status_code}')
            return response.json()
        raw=fetch_batch(get,start-pd.Timedelta(seconds=2),end,SYMBOLS)
        raw.update(identity=identity,retrieved_utc=datetime.now(timezone.utc).isoformat())
        save_once_or_identical(path,json.dumps(raw,allow_nan=False).encode())
    windows=[]
    for symbol in SYMBOLS:
        quotes=raw['quotes'].get(symbol,[])
        features=quote_features(quotes,start,end);last=latest_state(quotes,end)
        status=features['status']
        if status=='usable' and (last is None or last['full_spread_bps']>20): status='ineligible_terminal_spread'
        windows.append(dict(date=date,symbol=symbol,status=status,last=last,raw_quotes=len(quotes),
            fresh_coverage_pct=features['fresh_coverage_pct']))
    return dict(date=date,status='complete_historical_iex',pages=raw['pages'],
        raw_quotes=sum(len(items) for items in raw['quotes'].values()),windows=windows,
        cache_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def collect(original_plan,output):
    plan_source=original_plan.read_bytes();original=json.loads(plan_source)
    if original['protocol']['symbols']!=SYMBOLS: raise ValueError('Wrong matched study universe')
    output.mkdir(parents=True,exist_ok=True);cache=output/'quotes';cache.mkdir(exist_ok=True)
    plan=dict(protocol=PROTOCOL,dates=original['dates'],bar_cache_sha256=original['bar_cache_sha256'],
        original_date_plan_sha256=hashlib.sha256(plan_source).hexdigest())
    save_once_or_identical(output/'request_plan.json',json.dumps(plan,indent=2).encode())
    load_dotenv();rate=RateGate();report=dict(status='historical_mixed_feed_research_only',plan=plan,dates=[],orders=False)
    def work(date):
        try: return collect_date(date,cache,rate)
        except Exception as error: return dict(date=date,status='iex_fetch_failed',error_type=type(error).__name__)
    with ThreadPoolExecutor(max_workers=2) as pool:
        for index,result in enumerate(pool.map(work,plan['dates']),1):
            report['dates'].append(result)
            (output/'collection_status.json').write_text(json.dumps(report,indent=2,allow_nan=False))
            if index%10==0 or index==len(plan['dates']):
                print(json.dumps(dict(completed_dates=index,total_dates=len(plan['dates']),
                    usable_windows=sum(w['status']=='usable' for d in report['dates'] for w in d.get('windows',[])),
                    failed_dates=sum(d['status']=='iex_fetch_failed' for d in report['dates']))),flush=True)
    return report


def matched_rows(data,collection):
    payload=json.loads((collection/'collection_status.json').read_text());plan=payload['plan']
    if plan['protocol']!=PROTOCOL: raise ValueError('Changed mixed-feed protocol')
    keys=[row['date'] for row in payload['dates']]
    if len(keys)!=len(set(keys)) or set(keys)!=set(plan['dates']): raise ValueError('Incomplete/duplicate IEX collection')
    by_date,evidence=load_universe(data)
    if evidence['hashes']!=plan['bar_cache_sha256']: raise ValueError('Context bar inputs changed')
    base={(row['date'],row['symbol']):row for row in extended_rows(by_date)}
    rows=[];excluded=[];hashes={}
    for day in payload['dates']:
        date=day['date']
        if day['status']=='iex_fetch_failed': excluded.append(dict(date=date,reason='IEX fetch failure'));continue
        path=collection/'quotes'/f'{date}.json';content=path.read_bytes()
        if hashlib.sha256(content).hexdigest()!=day['cache_sha256']: raise ValueError('Changed retained IEX quote bytes')
        raw=json.loads(content);start,end,context,entry=bounds(date)
        identity=dict(date=date,symbols=SYMBOLS,feed='iex',start=start.isoformat(),cutoff=end.isoformat(),seed_seconds=2)
        if raw.get('identity')!=identity or raw.get('pagination_complete') is not True:
            raise ValueError('IEX cache identity/completeness mismatch')
        hashes[str(path)]=day['cache_sha256']
        for symbol in SYMBOLS:
            quotes=raw['quotes'].get(symbol,[]);features=quote_features(quotes,start,end);last=latest_state(quotes,end)
            if features['status']!='usable' or last is None or last['full_spread_bps']>20:
                excluded.append(dict(date=date,symbol=symbol,reason='Known-prefix IEX coverage/spread ineligible'));continue
            original=base[(date,symbol)];ratio=last['mid']/original['signal_price']
            if not .5<=ratio<=1.5:
                excluded.append(dict(date=date,symbol=symbol,reason='Quote/context price sanity failure'));continue
            # The same observable fresh midpoint fixes the signal/limit in
            # both arms; no favorable future open replaces the known quote.
            rows.append(dict(original,signal_price=last['mid'],
                quote_features=features['features']+[ratio-1],
                iex_quote_timestamp=last['timestamp'],iex_cutoff_utc=end.isoformat(),
                sip_context_cutoff_utc=context.isoformat(),hypothetical_entry_utc=entry.isoformat()))
    return rows,by_date,dict(bar_evidence=evidence,quote_cache_sha256=hashes,exclusions=excluded,
        planned_dates=plan['dates'],retained_candidates=len(rows))


def run(data,collection,output):
    output.mkdir(parents=True,exist_ok=True);rows,by_date,evidence=matched_rows(data,collection)
    report=dict(status='exposed_historical_mixed_feed_exploration_only',protocol=PROTOCOL,evidence=evidence,
        model_protocol=dict(models=MODELS,thresholds=[.5,.65,.9],warmup_dates=100,calibration_dates=30,
            test_block_dates=20,horizon='target_60',cost_bps_each_side=10,stock_cap=.01,category_cap=.05,
            max_positions=3,stop_fraction=.01,target_fraction=.004),
        quote_feature_names=FEATURES+['fresh_iex_mid_vs_delayed_sip_close'],
        source_sha256={name:hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for name in ['hybrid_iex_research.py','quote_feature_ablation.py','quote_microstructure_research.py',
                'regime_predictive_research.py','predictive_portfolio_research.py','quantum_kernel_research.py']},
        cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['All historical dates are exposed; no externally anchored future prediction',
            'IEX single-venue BBO is NOT consolidated SIP/NBBO or full order book',
            'Latest IEX HTTP access does not authenticate historical original receipt latency',
            'Thirty-second real collector/inference/upload budget remains unverified',
            'Both arms use a newly declared fresh-quote limit; not an attribution study versus the old frozen control',
            'Sampled dates/current universe/complete-session exclusions remain biased',
            'Quote conditions/actual executable size and whole-account intraday guards not validated',
            'Kernel is four-qubit CPU simulation, not quantum hardware or advantage'])
    for model in MODELS:
        for use_quotes in [False,True]:
            predictions,folds=walk(rows,by_date,model,use_quotes)
            case=dict(model=model,feature_set='context_plus_iex' if use_quotes else 'matched_context_fresh_limit',folds=folds,outcomes=[])
            for threshold in [.5,.65,.9]:
                for cost,delay in [(10,16),(20,16),(10,17)]:
                    result=portfolio(predictions,by_date,30,'target_60',threshold,cost,delay)
                    result.update(metrics=accounting_metrics(result,predictions),cost_diagnostic=diagnostic(result))
                    case['outcomes'].append(result)
                    if cost==10 and delay==16:
                        print(json.dumps(dict(model=model,features=case['feature_set'],threshold=threshold,
                            active_days=result['active_days'],net_usd=result['profit_usd'],win_rate=result['active_day_win_rate_pct'],
                            screen_pass=result['target_screen_pass'])),flush=True)
            report['cases'].append(case)
            (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['collect','evaluate'])
    parser.add_argument('--original-plan',type=Path,default=Path('research_runs/quote_microstructure/request_plan.json'))
    parser.add_argument('--collection',type=Path,default=Path('research_runs/hybrid_iex'))
    parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/hybrid_iex_evaluation'))
    args=parser.parse_args()
    if args.mode=='collect': collect(args.original_plan,args.collection)
    else: run(args.data,args.collection,args.output)
