"""Local prospective research control: fit/freeze or collect, NEVER orders.

Collector is not scheduled by this module. joblib inputs must be OWN frozen
artifacts; artifact hash is verified before deserialization. Local evidence
still needs an external timestamp anchor and outcome/execution evaluation.
"""
import argparse
from datetime import datetime,timedelta,time,timezone
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import requests
import sklearn
from dotenv import load_dotenv

from active_stock_research import SYMBOLS,load_universe
from predictive_portfolio_research import partition,path_outcome,FEATURES
from regime_predictive_research import extended_rows,EXTRA_FEATURES,fit_forecasters,predict_forecasters
import prospective_forecast_evidence as evidence

SOURCES=['prospective_model_collector.py','prospective_forecast_evidence.py',
    'regime_predictive_research.py','predictive_portfolio_research.py',
    'predictive_research.py','active_stock_research.py','intraday_research.py',
    'fixed_trade_cost_diagnostic.py']


def freeze_control(data,directory,forward_start,training_end='2026-10-01'):
    if (directory/'manifest.json').exists() or (directory/'model.joblib').exists():
        raise ValueError('Existing control experiment cannot be replaced')
    by_date,input_evidence=load_universe(data)
    by_date={d:stocks for d,stocks in by_date.items() if d<=training_end}
    rows=extended_rows(by_date)
    dates=sorted({r['date'] for r in rows})
    if len(dates)<240 or dates[-1]!=training_end:
        raise ValueError('Insufficient dated history or requested end date absent')
    outcomes={(r['date'],r['symbol']):path_outcome(by_date[r['date']][r['symbol']][0],
        r['signal_price'],30,'target_60',delay=16) for r in rows}
    train,cal=[partition(rows,part) for part in [dates[:-60],dates[-60:]]]
    train=[r for r in train if outcomes[(r['date'],r['symbol'])]['filled']]
    cal=[r for r in cal if outcomes[(r['date'],r['symbol'])]['filled']]
    fitted=fit_forecasters(train,cal,outcomes)
    artifact=dict(mode='prospective_research_control_only',production_approved=False,
        broker_orders_enabled=False,trained_through=training_end,feed='sip',
        sklearn_version=sklearn.__version__,features=FEATURES+EXTRA_FEATURES,
        symbols=list(SYMBOLS),input_evidence=input_evidence,
        training_last=dates[-61],calibration_first=dates[-60],calibration_last=dates[-1],
        rule=dict(feature_cutoff_minute=30,information_delay_minutes=15,
            execution_latency_minutes=1,horizon='target_60',threshold=.65,
            per_side_cost_bps=10,category_cap_fraction=.05,stock_cap_fraction=.01,
            max_positions=3,stop_fraction=.01,target_fraction=.004),fitted=fitted,
        prior_exploration_failed_target=True)
    directory.mkdir(parents=True,exist_ok=True)
    model_path=directory/'model.joblib'
    joblib.dump(artifact,model_path)
    envelope=evidence.freeze(directory,model_path,SOURCES,training_end,forward_start)
    evidence.write_once(directory/'control_description.json',
        {k:v for k,v in artifact.items() if k!='fitted'})
    print(json.dumps(dict(status='frozen_research_control_not_trading_candidate',
        manifest_sha256=envelope['manifest_sha256'],artifact_bytes=model_path.stat().st_size,
        training_rows=len(train),calibration_rows=len(cal),forward_records=0)))
    return artifact


def current_context(prior,current,session_date):
    if any(d>=session_date for d in prior):
        raise ValueError('History must strictly precede current session')
    if set(current)!=set(SYMBOLS):
        raise ValueError('Complete fixed-universe opening packet required')
    combined=dict(prior)
    today={}
    for symbol in SYMBOLS:
        a=np.asarray(current[symbol],dtype=float)
        if a.shape!=(30,5) or not np.isfinite(a).all() or (a[:,:4]<=0).any() or (a[:,4]<0).any():
            raise ValueError('Invalid opening OHLCV packet')
        if (a[:,1]<a[:,2]).any() or (a[:,1]<a[:,[0,3]].max(axis=1)).any() or (a[:,2]>a[:,[0,3]].min(axis=1)).any():
            raise ValueError('Inconsistent OHLC prices')
        past=[stocks[symbol][0] for _,stocks in sorted(prior.items()) if symbol in stocks]
        if len(past)<21: raise ValueError('Insufficient prior complete-session features')
        average_volume=float(np.mean([p[:5,4].sum() for p in past[-20:]]))
        info=dict(relative_volume=float(a[:5,4].sum()/average_volume) if average_volume else 0,
            prior_dollars=float(np.mean([np.dot(p[:,3],p[:,4]) for p in past[-20:]])))
        today[symbol]=(a,info)
    combined[session_date]=today
    rows=[r for r in extended_rows(combined) if r['date']==session_date]
    if len(rows)!=len(SYMBOLS): raise ValueError('Missing eligible symbols; retain skipped-session evidence')
    return rows


def get_json(url,params):
    headers={'APCA-API-KEY-ID':os.environ['ALPACA_API_KEY'],
        'APCA-API-SECRET-KEY':os.environ['ALPACA_API_SECRET']}
    response=requests.get(url,headers=headers,params=params,timeout=15)
    if response.status_code!=200:
        raise RuntimeError(f'Read-only API HTTP {response.status_code}; no forecast claimed')
    return response.json()


def collect(directory,history):
    envelope=evidence.read_manifest(directory)
    manifest=envelope['manifest']
    now=evidence.utc_now();local=now.astimezone(ZoneInfo('America/New_York'))
    session=str(local.date())
    cutoff=datetime.combine(local.date(),time(10),ZoneInfo('America/New_York'))
    available=cutoff+timedelta(minutes=15)
    deadline=available+timedelta(minutes=1)
    if local.weekday()>=5 or session<manifest['forward_start'] or not available<=now<deadline:
        raise ValueError('Outside the prospective collection window; no backfill allowed')
    path=directory/'model.joblib'
    if evidence.file_digest(path)!=manifest['artifact_sha256']:
        raise ValueError('Changed model; not deserialized')
    for source,expected in manifest['source_sha256'].items():
        if evidence.file_digest(source)!=expected: raise ValueError('Changed source; collector refused')
    # Precompute history BEFORE requests; slow runs miss the deadline safely.
    prior,_=load_universe(history)
    prior={d:stocks for d,stocks in prior.items() if d<session}
    dates=sorted(prior)
    if not dates or (local.date()-datetime.fromisoformat(dates[-1]).date()).days>4:
        raise ValueError('Historical context stale; refresh before collection window')
    artifact=joblib.load(path)
    if artifact.get('mode')!='prospective_research_control_only' or artifact.get('sklearn_version')!=sklearn.__version__:
        raise ValueError('Incompatible own research-control artifact')
    if artifact.get('features')!=FEATURES+EXTRA_FEATURES or artifact.get('feed')!='sip':
        raise ValueError('Input schema/feed mismatch')
    calendar=get_json('https://paper-api.alpaca.markets/v2/calendar',{'start':session,'end':session})
    if not calendar or calendar[0].get('date')!=session: raise ValueError('Not an exchange session')
    raw=get_json('https://data.alpaca.markets/v2/stocks/bars',dict(symbols=','.join(SYMBOLS),
        timeframe='1Min',feed='sip',adjustment='raw',limit=10000,
        start=(cutoff-timedelta(minutes=30)).astimezone(timezone.utc).isoformat(),
        end=(cutoff-timedelta(microseconds=1)).astimezone(timezone.utc).isoformat()))
    received=evidence.utc_now()
    if raw.get('next_page_token'): raise ValueError('Incomplete opening packet; no forecast recorded')
    current={s:np.array([[r[k] for k in ['o','h','l','c','v']] for r in sorted(records,key=lambda r:r['t'])])
        for s,records in raw.get('bars',{}).items()}
    rows=current_context(prior,current,session)
    forecasts=predict_forecasters(artifact['fitted'],rows)
    predictions=[dict(symbol=r['symbol'],**{k:float(v[i]) for k,v in forecasts.items()}) for i,r in enumerate(rows)]
    raw_path=(directory/'receipts'/f'{session}_bars.json').resolve()
    calendar_path=(directory/'receipts'/f'{session}_calendar.json').resolve()
    evidence.write_once(raw_path,raw);evidence.write_once(calendar_path,calendar)
    receipt=dict(feed='sip',calendar_session_date=session,feature_cutoff_utc=cutoff.astimezone(timezone.utc).isoformat(),
        last_bar_end_utc=cutoff.astimezone(timezone.utc).isoformat(),received_utc=received.isoformat(),
        raw_response_path=str(raw_path),calendar_response_path=str(calendar_path),
        raw_response_sha256=evidence.file_digest(raw_path),calendar_response_sha256=evidence.file_digest(calendar_path))
    packet=evidence.capture(directory,path,session,receipt,predictions)
    print(json.dumps(dict(status='local_prospective_research_forecast',record_sha256=packet['record_sha256'],
        predictions=len(predictions),orders=False,external_anchor_verified=False)))
    return packet


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['freeze','collect','inspect'])
    parser.add_argument('--directory',type=Path,default=Path('research_runs/prospective_control_v1'))
    parser.add_argument('--data',type=Path,default=Path('cache/active_stocks'))
    parser.add_argument('--forward-start',default='2026-10-12')
    args=parser.parse_args();load_dotenv()
    if args.mode=='freeze': freeze_control(args.data,args.directory,args.forward_start)
    elif args.mode=='collect': collect(args.directory,args.data)
    else: print(json.dumps(evidence.inspect(args.directory)))
