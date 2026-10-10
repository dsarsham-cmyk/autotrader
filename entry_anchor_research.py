"""Past-only opening-VWAP pullback entry versus close anchor; no orders."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
from active_stock_research import load_universe
from regime_predictive_research import extended_rows,vwap
from reward_policy_research import walk
from reward_policy_simulator import portfolio
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic

PROTOCOL=dict(policies=['opening_close','opening_vwap_pullback'],models=['logistic','boosted'],
    thresholds=[.5,.65,.9],features='unchanged 21 opening/prior-session features',
    cutoff_minute=30,information_delay=15,entry_delay=16,horizon=60,
    stop=.01,target=.004,cost_per_side_bps=10,stock_cap=.01,category_cap=.05,
    max_positions=3,planned_trade_risk=.0005,orders=False,production_approved=False)


def anchor_rows(rows,by_date,policy):
    if policy not in PROTOCOL['policies']: raise ValueError('Unknown entry policy')
    result=[]
    for row in rows:
        a=np.asarray(by_date[row['date']][row['symbol']][0],dtype=float)
        price=float(a[29,3])
        if policy=='opening_vwap_pullback': price=min(price,vwap(a,30))
        if not np.isfinite(price) or price<=0: raise ValueError('Invalid entry anchor')
        result.append(dict(row,signal_price=price,entry_policy=policy))
    return result


def run(data,reference,output):
    original=json.loads(reference.read_text())
    if original['status']!='completed_exposed_historical_reward_research':
        raise ValueError('Completed reward reference required')
    for name,value in original['dependency_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=value:
            raise ValueError('Reference source changed')
    by_date,evidence=load_universe(data)
    if evidence['hashes']!=original['evidence']['hashes']: raise ValueError('Reference input changed')
    rows=extended_rows(by_date);output.mkdir(parents=True,exist_ok=True)
    report=dict(status='running_exposed_entry_anchor_research',protocol=PROTOCOL,evidence=evidence,
        reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        dependency_sha256=dict(original['dependency_sha256'],**{
            'entry_anchor_research.py':hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest()}),
        cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Exposed historical dates; not independent validation or best-policy selection',
            'VWAP uses first30 HLC3 minute-bar volume weighting, not trade-by-trade VWAP',
            'VWAP limit never exceeds close limit; fewer fills can change coverage and conditional labels',
            'Only entry at next eligible modeled opening; no hindsight intrabar fill or waiting for a later dip',
            'Policy-specific past filled labels are refitted; test forecasts precede unknown fills',
            'Existing fixed-universe, raw corporate-action, SIP completeness and OHLC guard limitations remain'])
    with threadpool_limits(limits=1):
        for policy in PROTOCOL['policies']:
            inputs=anchor_rows(rows,by_date,policy)
            for kind in PROTOCOL['models']:
                predictions,folds=walk(inputs,by_date,.004,kind)
                case=dict(entry_policy=policy,model=kind,folds=folds,outcomes=[])
                for threshold in PROTOCOL['thresholds']:
                    for cost,delay in [(10,16),(20,16),(10,17)]:
                        result=portfolio(predictions,by_date,.004,threshold,cost,delay)
                        result.update(metrics=accounting_metrics(result,predictions),cost_diagnostic=diagnostic(result))
                        if policy=='opening_close':
                            old=next(c for c in original['cases'] if c['target_fraction']==.004 and c['model']==kind)
                            expected=next(o for o in old['outcomes'] if (o['threshold'],o['costs_bps'],o['delay'])==(threshold,cost,delay))
                            if any(result[k]!=expected[k] for k in ['profit_usd','active_days','daily','trades']):
                                raise ValueError('Original close reference not reproduced')
                        case['outcomes'].append(result)
                        if cost==10 and delay==16:
                            print(json.dumps(dict(policy=policy,model=kind,threshold=threshold,
                                active_days=result['active_days'],win_rate=result['active_day_win_rate_pct'],
                                net_usd=result['profit_usd'],screen_pass=result['target_screen_pass'])),flush=True)
                report['cases'].append(case)
                (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_entry_anchor_research'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--reference',type=Path,default=Path('research_runs/reward_policy/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/entry_anchor'))
    a=p.parse_args();run(a.data,a.reference,a.output)
