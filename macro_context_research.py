"""Read-only ETF context ablation; these proxies are features, not positions.

Matched predecision context eligibility; missing sessions remain abstention.
No macro causal claim, spot-index substitution, orders or strategy promotion.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from active_stock_research import load_universe,fetch_symbol,hash_file
from regime_predictive_research import extended_rows
from premarket_predictive_research import walk
from tighter_stop_simulator import portfolio
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic

PROXIES=['SPY','TLT','UUP','GLD']
PROTOCOL=dict(proxies=PROXIES,proxy_positions=False,feature_sets=['summary_matched','summary_plus_macro'],
    models=['logistic','boosted','mlp'],opening_cutoff_minute=30,minimum_opening_bars=5,
    last_opening_bar_minute_at_least=598,prior_sessions=21,information_delay_minutes=15,
    entry_delay=16,thresholds=[.5,.65,.9],cost_bps=10,stop_fraction=.01,
    target_fraction=.004,horizon_minutes=60,orders=False,production_approved=False)
FIELDS=['return','range','location','vwap_distance','observed_return_volatility',
    'log1p_relative_volume','gap','prior_five_return','prior_volatility','opening_coverage']


def download(directory):
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent/'.env');directory.mkdir(parents=True,exist_ok=True)
    def one(symbol):
        target=directory/f'{symbol}.csv'
        if target.exists() or target.with_suffix('.metadata.json').exists():
            raise ValueError('Existing macro cache is not overwritten; use evaluation without --download')
        fetch_symbol(symbol,directory,'2024-01-01','2026-10-02')
    with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(one,PROXIES))


def proxy_sessions(frame,symbol):
    if set(frame.symbol)!={symbol}: raise ValueError('Wrong ETF context symbol')
    if not frame.timestamp.astype(str).str.contains(r'(?:Z|[+-]\d{2}:\d{2})$').all():
        raise ValueError('Explicit timezone required')
    utc=pd.to_datetime(frame.timestamp,utc=True)
    if utc.duplicated().any() or (utc.dt.second!=0).any() or (utc.dt.microsecond!=0).any() or (utc.dt.nanosecond!=0).any():
        raise ValueError('Unique exact minute timestamps required')
    ny=utc.dt.tz_convert('America/New_York');minute=ny.dt.hour*60+ny.dt.minute
    regular=frame.loc[(minute>=570)&(minute<960)].copy()
    regular['date']=ny.loc[regular.index].dt.strftime('%Y-%m-%d')
    regular['minute']=minute.loc[regular.index]
    a=regular[['open','high','low','close','volume']].to_numpy(dtype=float)
    if not np.isfinite(a).all() or (a[:,:4]<=0).any() or (a[:,4]<0).any(): raise ValueError('Invalid ETF OHLCV')
    if (a[:,1]<a[:,[0,3]].max(axis=1)).any() or (a[:,2]>a[:,[0,3]].min(axis=1)).any():
        raise ValueError('Inconsistent ETF OHLC')
    return {date:group.sort_values('minute').reset_index(drop=True) for date,group in regular.groupby('date',sort=True)}


def load_context(directory):
    observations={};evidence={}
    for symbol in PROXIES:
        filename=directory/f'{symbol}.csv';meta=json.loads(filename.with_suffix('.metadata.json').read_text())
        actual=hash_file(filename)
        if meta.get('feed')!='sip' or meta.get('adjustment')!='raw' or meta.get('sha256')!=actual:
            raise ValueError('ETF source SIP/raw byte hash mismatch')
        frame=pd.read_csv(filename);observations[symbol]=proxy_sessions(frame,symbol)
        evidence[symbol]=dict(source_sha256=actual,rows=len(frame),regular_dates=len(observations[symbol]),metadata=meta)
    return observations,evidence


def context(opening,prior):
    if len(prior)<21: return None,'insufficient_prior_context'
    if opening is None or opening.empty: return None,'missing_opening_context'
    if not opening.minute.between(570,599).all() or opening.minute.duplicated().any() or not opening.minute.is_monotonic_increasing:
        raise ValueError('ETF opening cutoff/order violation')
    if len(opening)<5 or opening.minute.iloc[-1]<598: return None,'sparse_or_stale_context'
    a=opening[['open','high','low','close','volume']].to_numpy(dtype=float)
    volume=float(a[:,4].sum());past_volume=float(np.mean([p['volume'] for p in prior[-20:]]))
    if volume<=0 or past_volume<=0: return None,'zero_context_volume'
    first=float(a[0,0]);last=float(a[-1,3]);hi=float(a[:,1].max());lo=float(a[:,2].min())
    vwap=float(np.dot((a[:,1]+a[:,2]+a[:,3])/3,a[:,4])/volume)
    closes=np.asarray([p['close'] for p in prior[-21:]],dtype=float)
    values=[last/first-1,(hi-lo)/first,(last-lo)/(hi-lo) if hi>lo else .5,last/vwap-1,
        float(np.sqrt(np.sum(np.diff(np.log(np.r_[first,a[:,3]]))**2))),
        float(np.log1p(volume/past_volume)),first/closes[-1]-1,closes[-1]/closes[-6]-1,
        float(np.std(np.diff(np.log(closes)))),len(opening)/30]
    if not np.isfinite(values).all(): raise ValueError('Nonfinite ETF features')
    return values,'eligible'


def contexts(observations):
    """Today's closing bar is appended AFTER today's opening feature extraction."""
    results={};reasons={}
    for symbol in PROXIES:
        prior=[];results[symbol]={}
        for date,regular in sorted(observations[symbol].items()):
            opening=regular.loc[regular.minute<600]
            values,reason=context(opening,prior)
            results[symbol][date]=values;reasons[(date,symbol)]=reason
            # Do not require today's future closing bar to accept its opening.
            close=regular.loc[regular.minute==959]
            if not close.empty:
                prior.append(dict(date=date,close=float(close.close.iloc[0]),volume=float(opening.volume.sum())))
    return results,reasons


def matched_rows(by_date,observations):
    values,reasons=contexts(observations);rows=[];eligibility={}
    for row in extended_rows(by_date):
        date=row['date'];ready=all(values[s].get(date) is not None for s in PROXIES)
        reason='eligible' if ready else '|'.join(s+':'+reasons.get((date,s),'missing_proxy_session')
            for s in PROXIES if values[s].get(date) is None)
        eligibility[reason]=eligibility.get(reason,0)+1
        extra=[v for s in PROXIES for v in values[s][date]] if ready else [0.]*40
        # Equity-relative opening moves are available at the same cutoff.
        extra.extend([row['features'][0]-values['SPY'][date][0],
            row['features'][1]-values['SPY'][date][6]] if ready else [0.,0.])
        rows.append(dict(row,features=row['features']+extra,predecision_eligible=ready,
            context_kind='macro_etf',eligibility_reason=reason))
    return rows,eligibility


def run(data,macro,output):
    output.mkdir(parents=True,exist_ok=True);by_date,evidence=load_universe(data)
    observations,macro_evidence=load_context(macro);full,eligibility=matched_rows(by_date,observations)
    report=dict(status='running_exposed_historical_macro_research',protocol=PROTOCOL,
        extra_features=[s+'_'+f for s in PROXIES for f in FIELDS]+['equity_minus_spy_opening_return','equity_minus_spy_gap'],
        evidence=evidence,macro_evidence=macro_evidence,eligibility_counts=eligibility,
        dependency_sha256={n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['macro_context_research.py','premarket_predictive_research.py','neural_convergence_research.py',
                'regime_predictive_research.py','predictive_portfolio_research.py','predictive_research.py',
                'tighter_stop_simulator.py','active_stock_research.py']},
        cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Previously exposed stock outcomes; newly fetched proxy inputs do not make outcomes independent',
            'ETFs are imperfect proxies, not actual spot rates, exchange rates, causal macro announcements or book depth',
            'Sparse ETF opening bars and incomplete past closes affect eligibility, which is matched in both arms',
            'Current universe, full-session stock exclusions, raw splits/revisions and assumed SIP receipt remain biased',
            'OHLC fills and approximate EOD account guards are not validated actual execution'])
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
    report['status']='completed_exposed_historical_macro_research'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--macro',type=Path,default=Path('cache/macro_context_sip'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/macro_context'))
    parser.add_argument('--download',action='store_true');args=parser.parse_args()
    if args.download: download(args.macro)
    run(args.data,args.macro,args.output)
