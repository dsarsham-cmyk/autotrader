"""Matched ablation of 08:00-09:30 NY SIP premarket context, no orders.

Premarket eligibility is predecision, equal in both arms. Ineligible observed
sessions are retained as abstention, not removed or counted as wins.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from active_stock_research import load_universe,SYMBOLS,hash_file
from regime_predictive_research import extended_rows
from predictive_portfolio_research import partition,fit_predict
from neural_convergence_research import fit_probability as fit_neural
from tighter_stop_simulator import path,portfolio
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic

FEATURES=['premarket_return','premarket_range','premarket_close_location',
    'premarket_distance_vwap','premarket_observed_return_volatility','log1p_relative_premarket_volume',
    'opening_gap_from_last_premarket','opening_close_vs_premarket_vwap',
    'premarket_observed_bar_fraction','premarket_terminal_age_fraction']
PROTOCOL=dict(feature_sets=['summary_matched','summary_plus_premarket'],models=['logistic','boosted','mlp'],
    window='08:00 inclusive to 09:30 exclusive America/New_York',minimum_bars=5,
    minimum_last_bar_start='09:25 NY',prior_volume_sessions=20,
    warmup_dates=240,calibration_dates=60,test_block_dates=20,thresholds=[.5,.65,.9],
    feed='sip',adjustment='raw',opening_cutoff_minute=30,information_delay_minutes=15,
    entry_delay=16,cost_bps=10,stop_fraction=.01,target_fraction=.004,horizon_minutes=60,
    matched_predecision_eligibility=True,orders=False,independent_validation_pass=False)


def windows(frame,symbol):
    if not {'symbol','timestamp','open','high','low','close','volume'}<=set(frame.columns):
        raise ValueError('Missing premarket source columns')
    if set(frame.symbol)!={symbol}: raise ValueError('Wrong premarket symbol')
    if not frame.timestamp.astype(str).str.contains(r'(?:Z|[+-]\d{2}:\d{2})$').all():
        raise ValueError('Explicit timezone required')
    timestamps=pd.to_datetime(frame.timestamp,utc=True)
    if timestamps.duplicated().any() or (timestamps.dt.second!=0).any() or (timestamps.dt.microsecond!=0).any() or (timestamps.dt.nanosecond!=0).any():
        raise ValueError('Unique exact minute timestamps required')
    ny=timestamps.dt.tz_convert('America/New_York');minute=ny.dt.hour*60+ny.dt.minute
    chosen=frame.loc[(minute>=480)&(minute<570)].copy()
    chosen['date']=ny.loc[chosen.index].dt.strftime('%Y-%m-%d')
    chosen['minute']=minute.loc[chosen.index]
    chosen['utc_timestamp']=timestamps.loc[chosen.index]
    a=chosen[['open','high','low','close','volume']].to_numpy(dtype=float)
    if not np.isfinite(a).all() or (a[:,:4]<=0).any() or (a[:,4]<0).any(): raise ValueError('Invalid premarket OHLCV')
    if (a[:,1]<a[:,[0,3]].max(axis=1)).any() or (a[:,2]>a[:,[0,3]].min(axis=1)).any():
        raise ValueError('Inconsistent premarket OHLC')
    return {date:group.sort_values('utc_timestamp').reset_index(drop=True)
        for date,group in chosen.groupby('date',sort=True)}


def load_windows(directory):
    result={};provenance={}
    for symbol in SYMBOLS:
        filename=directory/f'{symbol}.csv';metadata=json.loads(filename.with_suffix('.metadata.json').read_text())
        actual=hash_file(filename)
        if metadata.get('feed')!='sip' or metadata.get('adjustment')!='raw' or metadata.get('sha256')!=actual:
            raise ValueError('Premarket source SIP/raw byte hash mismatch')
        result[symbol]=windows(pd.read_csv(filename),symbol)
        provenance[symbol]=dict(source_sha256=actual,window_dates=len(result[symbol]),
            observed_premarket_bars=sum(len(w) for w in result[symbol].values()))
    return result,provenance


def context(window,prior_volumes,opening):
    if len(prior_volumes)<20: return None,'insufficient_prior_window_history'
    if window is None or window.empty: return None,'missing_window'
    if not window.minute.between(480,569).all() or window.minute.duplicated().any() or not window.minute.is_monotonic_increasing:
        raise ValueError('Invalid premarket cutoff/order')
    if len(window)<5 or int(window.minute.iloc[-1])<565: return None,'sparse_or_stale_window'
    a=window[['open','high','low','close','volume']].to_numpy(dtype=float)
    past=np.asarray(prior_volumes[-20:],dtype=float)
    if not np.isfinite(past).all() or (past<0).any(): raise ValueError('Invalid prior volume')
    volume=float(a[:,4].sum());benchmark=float(past.mean())
    if volume<=0 or benchmark<=0: return None,'zero_volume_context'
    first=float(a[0,0]);last=float(a[-1,3]);high=float(a[:,1].max());low=float(a[:,2].min())
    vwap=float(np.dot((a[:,1]+a[:,2]+a[:,3])/3,a[:,4])/volume)
    log_returns=np.diff(np.log(np.r_[first,a[:,3]]))
    features=[last/first-1,(high-low)/first,(last-low)/(high-low) if high>low else .5,
        last/vwap-1,float(np.sqrt(np.sum(log_returns**2))),float(np.log1p(volume/benchmark)),
        float(opening[0,0]/last-1),float(opening[29,3]/vwap-1),len(window)/90,
        (570-int(window.minute.iloc[-1])-1)/90]
    if not np.isfinite(features).all(): raise ValueError('Nonfinite premarket features')
    return features,'eligible'


def matched_rows(by_date,observations):
    base={(r['date'],r['symbol']):r for r in extended_rows(by_date)}
    histories={};rows=[];eligibility={}
    for date,stocks in sorted(by_date.items()):
        for symbol,(a,_) in sorted(stocks.items()):
            past=histories.setdefault(symbol,[]);window=observations.get(symbol,{}).get(date)
            key=(date,symbol)
            if key in base:
                extra,reason=context(window,past,a)
                eligibility[reason]=eligibility.get(reason,0)+1
                rows.append(dict(base[key],features=base[key]['features']+(extra if extra is not None else [0.]*10),
                    predecision_eligible=extra is not None,eligibility_reason=reason))
            # Only completed PAST dates enter tomorrow's volume benchmark.
            past.append(float(window.volume.sum()) if window is not None else 0.)
    return rows,eligibility


def walk(rows,by_date,kind):
    if kind not in PROTOCOL['models']: raise ValueError('Unknown model')
    dates=sorted({r['date'] for r in rows})
    outcomes={(r['date'],r['symbol']):path(by_date[r['date']][r['symbol']][0],r['signal_price'],.01,10,16) for r in rows}
    labels={k:o['label'] for k,o in outcomes.items()};predictions=[];folds=[]
    for start in range(240,len(dates),20):
        parts=[dates[:start-60],dates[start-60:start],dates[start:start+20]]
        train,cal,all_test=[partition(rows,d) for d in parts]
        train=[r for r in train if r['predecision_eligible'] and outcomes[(r['date'],r['symbol'])]['filled']]
        cal=[r for r in cal if r['predecision_eligible'] and outcomes[(r['date'],r['symbol'])]['filled']]
        test=[r for r in all_test if r['predecision_eligible']]
        fit={};p=np.array([])
        if test:
            if kind=='mlp': p,fit=fit_neural(train,cal,test,labels)
            else: p=fit_predict(train,cal,test,kind,labels)
        forecasts={(r['date'],r['symbol']):float(v) for r,v in zip(test,p)}
        predictions.extend(dict(r,probability=forecasts.get((r['date'],r['symbol']),0),
            probability_is_forecast=r['predecision_eligible']) for r in all_test)
        filled=[i for i,r in enumerate(test) if outcomes[(r['date'],r['symbol'])]['filled']]
        folds.append(dict(train_last=parts[0][-1],calibration_first=parts[1][0],calibration_last=parts[1][-1],
            test_first=parts[2][0],test_last=parts[2][-1],fit=fit,eligible_test_rows=len(test),
            observed_test_rows=len(all_test),filled_eligible_test_samples=len(filled),
            brier_filled=float(np.mean([(p[i]-labels[(test[i]['date'],test[i]['symbol'])])**2 for i in filled])) if filled else None))
    return predictions,folds


def run(data,output):
    output.mkdir(parents=True,exist_ok=True);by_date,evidence=load_universe(data)
    observations,provenance=load_windows(data);full,eligibility=matched_rows(by_date,observations)
    report=dict(status='running_exposed_historical_premarket_research',protocol=PROTOCOL,features=FEATURES,
        evidence=evidence,premarket_provenance=provenance,eligibility_counts=eligibility,
        dependency_sha256={n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['premarket_predictive_research.py','neural_convergence_research.py','regime_predictive_research.py',
                'predictive_portfolio_research.py','predictive_research.py','tighter_stop_simulator.py','active_stock_research.py']},
        cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Already exposed historical dates; not independent evidence',
            'Premarket bars may be sparse and revised; historical timestamps do not authenticate original receipt',
            'Matched eligibility changes the sample versus earlier unfiltered reference, not only features',
            'Observed-bar volatility and typical-price VWAP are approximations, not tick/book features',
            'Current universe, complete-session exclusions, raw splits and OHLC/guard assumptions remain biased'])
    with threadpool_limits(limits=1):
        for feature_set in PROTOCOL['feature_sets']:
            rows=[dict(r,features=r['features'][:21]) for r in full] if feature_set=='summary_matched' else full
            for kind in PROTOCOL['models']:
                predictions,folds=walk(rows,by_date,kind)
                case=dict(feature_set=feature_set,model=kind,folds=folds,outcomes=[])
                for threshold in PROTOCOL['thresholds']:
                    for cost,delay in [(10,16),(20,16),(10,17)]:
                        result=portfolio(predictions,by_date,.01,threshold,cost,delay)
                        result.update(metrics=accounting_metrics(result,predictions),cost_diagnostic=diagnostic(result))
                        case['outcomes'].append(result)
                        if cost==10 and delay==16:
                            print(json.dumps(dict(features=feature_set,model=kind,threshold=threshold,
                                active_days=result['active_days'],win_rate=result['active_day_win_rate_pct'],
                                net_usd=result['profit_usd'],screen_pass=result['target_screen_pass'])),flush=True)
                report['cases'].append(case)
                (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_historical_premarket_research'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/premarket_predictive'))
    args=parser.parse_args();run(args.data,args.output)
