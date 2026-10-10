"""No-forecast controls for fresh IEX classifiers; not new trading strategies.

Five predeclared hash seeds, no best-seed selection. Same model-approved pool
tests ranking only; all-eligible control also changes gating. Neither creates
independent evidence or qualifies a strategy for promotion.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
from active_stock_research import load_universe
from iex_bar_predictive_research import load_iex,matched_rows,walk
from tighter_stop_simulator import portfolio
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic

PROTOCOL=dict(seeds=[11,23,37,53,71],models=['logistic','boosted','mlp','quantum_fidelity'],
    thresholds=[.5,.65,.9],entry_delay=1,cost_bps=10,stop_fraction=.01,
    target_fraction=.004,horizon_minutes=60,maximum_positions=3,
    null_score_is_probability=False,bootstrap_block_observed_sessions=20,
    bootstrap_samples=1024,bootstrap_seed=19,orders=False,production_approved=False)


def null_selection(predictions,seed,gate=None):
    if isinstance(seed,bool) or not isinstance(seed,int): raise ValueError('Integer control seed required')
    if gate is not None and (not math.isfinite(gate) or not 0<=gate<=1): raise ValueError('Invalid model gate')
    grouped={};seen=set()
    for row in predictions:
        key=(row['date'],row['symbol'])
        if key in seen: raise ValueError('Duplicate observed candidate')
        seen.add(key)
        p=row['probability']
        if not math.isfinite(p) or not 0<=p<=1: raise ValueError('Invalid source forecast')
        grouped.setdefault(row['date'],[]).append(row)
    selected=[]
    for date,rows in sorted(grouped.items()):
        pool=[r for r in rows if r['predecision_eligible'] and (gate is None or r['probability']>=gate)]
        # Hash ranking depends only on predeclared seed, date and symbol.
        chosen=sorted(pool,key=lambda r:(hashlib.sha256(f'{seed}|{date}|{r["symbol"]}'.encode()).digest(),r['symbol']))[:3]
        scores={r['symbol']:.9-.1*i for i,r in enumerate(chosen)}
        selected.extend(dict(r,forecast_probability=r['probability'],probability=scores.get(r['symbol'],0),
            selection_score_is_probability=False,control_seed=seed) for r in rows)
    return selected


def daily_returns(outcome):
    dates=[];values=[]
    for day in outcome['daily']:
        start=day['equity']-day['pnl']
        if not math.isfinite(start) or start<=0 or not math.isfinite(day['pnl']):
            raise ValueError('Invalid observed account series')
        dates.append(day['date']);values.append(day['pnl']/start)
    if dates!=sorted(set(dates)): raise ValueError('Unique chronological observed dates required')
    return dates,np.asarray(values)


def paired_comparison(model,controls):
    if not controls: raise ValueError('Controls required')
    dates,y=daily_returns(model);other=[]
    for control in controls:
        cdates,values=daily_returns(control)
        if cdates!=dates: raise ValueError('Model/control observation calendars differ')
        other.append(values)
    delta=y-np.mean(other,axis=0);n=len(delta)
    if n<40: raise ValueError('At least two fixed blocks of observed sessions required')
    rng=np.random.default_rng(PROTOCOL['bootstrap_seed']);block=20
    starts=rng.integers(0,n,size=(1024,math.ceil(n/block)))
    indices=(starts[:,:,None]+np.arange(block))%n
    samples=delta[indices.reshape(1024,-1)[:,:n]].mean(axis=1)*10000
    return dict(observed_sessions=n,mean_daily_model_advantage_bps=float(delta.mean()*10000),
        descriptive_block_bootstrap_interval_bps=np.quantile(samples,[.025,.975]).tolist(),
        mean_control_profit_usd=float(np.mean([c['profit_usd'] for c in controls])),
        mean_control_active_days=float(np.mean([c['active_days'] for c in controls])),
        seed_results_not_independent_market_samples=True,independent_validation_pass=False,
        note='Circular observed-session blocks are exploratory, not causal significance or a 90% accuracy guarantee')


def evaluated(predictions,by_date,gate):
    result=portfolio(predictions,by_date,.01,gate,10,1)
    result.update(metrics=accounting_metrics(result,predictions),cost_diagnostic=diagnostic(result))
    return result


def reference_match(actual,expected):
    if len(actual['trades'])!=len(expected['trades']): raise ValueError('Reference trade count changed')
    for key in ['profit_usd','active_days','active_day_win_rate_pct','worst_day_usd']:
        if actual[key]!=expected[key]: raise ValueError('Original reference outcome changed')
    for a,b in zip(actual['trades'],expected['trades']):
        if a!=b: raise ValueError('Original reference trade changed')


def run(data,iex,reference,output):
    original=json.loads(reference.read_text())
    if original['status']!='completed_exposed_historical_iex_bar_research': raise ValueError('Completed source study required')
    for name,value in original['dependency_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=value:
            raise ValueError('Source study dependency changed; do not compare silently')
    output.mkdir(parents=True,exist_ok=True);by_date,evidence=load_universe(data)
    observations,iex_evidence=load_iex(iex)
    if evidence['hashes']!=original['evidence']['hashes'] or any(
        v['source_sha256']!=original['iex_evidence'][s]['source_sha256'] for s,v in iex_evidence.items()):
        raise ValueError('Original study market inputs changed')
    rows,eligibility=matched_rows(by_date,observations)
    report=dict(status='running_exposed_historical_null_benchmark',protocol=PROTOCOL,
        reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),evidence=evidence,
        iex_evidence=iex_evidence,eligibility_counts=eligibility,
        dependency_sha256=dict(original['dependency_sha256'],**{
            'predictive_null_benchmark.py':hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest()}),
        all_eligible_controls=[],cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Exposed historical dates; no independent evidence or best-seed optimization',
            'Matched model-pool controls test ranking, not the value of the probability gate itself',
            'All-eligible control changes gating and fills; not an identical-coverage ranking comparison',
            'Fixed seeds are algorithmic controls, not independent trading days',
            'Descriptive bootstrap does not establish stationarity or correct repeated-experiment selection',
            'Existing fixed-universe, SIP completeness, raw split, live receipt and OHLC/guard limitations remain'])
    with threadpool_limits(limits=1):
        for kind in PROTOCOL['models']:
            predictions,folds=walk(rows,by_date,kind,1)
            if not report['all_eligible_controls']:
                for seed in PROTOCOL['seeds']:
                    selected=null_selection(predictions,seed)
                    report['all_eligible_controls'].append(dict(seed=seed,outcome=evaluated(selected,by_date,.5)))
            old=[c for c in original['cases'] if c['entry_delay']==1 and c['model']==kind][0]
            for threshold in PROTOCOL['thresholds']:
                model=evaluated(predictions,by_date,threshold)
                expected=[o for o in old['outcomes'] if o['threshold']==threshold and o['costs_bps']==10 and o['delay']==1][0]
                reference_match(model,expected)
                controls=[]
                for seed in PROTOCOL['seeds']:
                    selected=null_selection(predictions,seed,threshold)
                    controls.append(dict(seed=seed,outcome=evaluated(selected,by_date,.5)))
                paired=paired_comparison(model,[c['outcome'] for c in controls])
                report['cases'].append(dict(model=kind,probability_gate=threshold,model_outcome=model,
                    model_reference_reproduced=True,matched_pool_controls=controls,paired_comparison=paired))
                (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
                print(json.dumps(dict(model=kind,gate=threshold,net_usd=model['profit_usd'],
                    matched_control_mean_usd=paired['mean_control_profit_usd'],
                    mean_daily_advantage_bps=paired['mean_daily_model_advantage_bps'],
                    descriptive_interval_bps=paired['descriptive_block_bootstrap_interval_bps'])),flush=True)
    report['status']='completed_exposed_historical_null_benchmark'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--iex',type=Path,default=Path('cache/iex_bar_context'))
    parser.add_argument('--reference',type=Path,default=Path('research_runs/iex_bar_predictive/results.json'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/predictive_null'))
    args=parser.parse_args();run(args.data,args.iex,args.reference,args.output)
