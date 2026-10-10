"""Basket-day model on corrected causal candidates, never production approval."""
import argparse
import hashlib
import json
from pathlib import Path
from threadpoolctl import threadpool_limits
from causal_opening_inventory import load_observations
from causal_sparse_research import market_maps
from causal_sparse_simulator import portfolio
from daily_meta_research import day_features,meta_crossfit
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic
from finbert_comparison_audit import check

PROTOCOL=dict(base_stock_model='boosted',base_stock_gate=.65,meta_models=['logistic','boosted'],
    meta_gates=[.65,.9],meta_warmup_dates=120,meta_calibration_dates=30,meta_test_block=20,
    prices='corrected causal opening candidates, including sparse later sessions',
    label='positive basket-day net conditional on known past base activity',
    no_trade_days_are_wins=False,orders=False)


def records(forecasts,baseline):
    days={d['date']:d for d in baseline['daily']};grouped={}
    for r in forecasts: grouped.setdefault(r['date'],[]).append(r)
    result=[]
    for date,rows in sorted(grouped.items()):
        day=days.get(date)
        result.append(dict(date=date,features=day_features(rows),outcome_known=day is not None,
            base_active=bool(day and day['active']),base_net_pnl=day['pnl'] if day else None,
            label=int(day['pnl']>0) if day else None))
    return result


def gated(forecasts,probabilities,threshold):
    return [dict(r,stock_probability=r['probability'],day_probability=probabilities[r['date']],
        eligibility_gated=True,probability=r['probability'] if probabilities[r['date']] is not None
        and probabilities[r['date']]>=threshold else 0.) for r in forecasts if r['date'] in probabilities]


def run(data,reference,output):
    raw=reference.read_bytes();original=json.loads(raw)
    if original['status']!='completed_exposed_causal_sparse_research': raise ValueError('Completed reference required')
    for name,expected in original['dependency_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected:
            raise ValueError('Reference source changed')
    observations,evidence=load_observations(data)
    if evidence!=original['evidence']: raise ValueError('Reference observations changed')
    market=market_maps(observations);old=next(c for c in original['cases'] if c['model']=='boosted')
    forecasts=old['forecasts'];baseline=portfolio(forecasts,market,.65)
    expected=next(o for o in old['outcomes'] if (o['threshold'],o['costs_bps'],o['delay'])==(.65,10,16))
    if any(baseline[k]!=expected[k] for k in ['daily','trades','profit_usd','unknown_selections']):
        raise ValueError('Base stock control not reproduced')
    training=records(forecasts,baseline);test_dates={r['date'] for r in training[120:]}
    control=[r for r in forecasts if r['date'] in test_dates]
    output.mkdir(parents=True,exist_ok=True)
    report=dict(status='running_exposed_causal_daily_gate',protocol=PROTOCOL,evidence=evidence,
        reference_sha256=hashlib.sha256(raw).hexdigest(),
        dependency_sha256=dict(original['dependency_sha256'],**{n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['causal_daily_gate_research.py','daily_meta_research.py','finbert_comparison_audit.py']}),
        meta_training_records=training,cases=[],orders=False,independent_validation_pass=False,production_approved=False,
        limitations=['Exposed historical dates; not independent validation',
            'Labels describe cumulative base policy; gated share counts/capital can differ',
            'Unknown base outcomes cannot train/calibrate; all future feature dates retained',
            'Small past active-day calibration samples may prevent a forecast, not prove90% confidence',
            'Fixed universe/raw revisions/original receipts/modeled execution remain'])
    with threadpool_limits(limits=1):
        variants=[('base_control',None,None,control)]
        for model in PROTOCOL['meta_models']:
            probabilities,folds=meta_crossfit(training,model)
            for gate in PROTOCOL['meta_gates']:
                variants.append((model,gate,dict(probabilities=probabilities,folds=folds),gated(forecasts,probabilities,gate)))
        for model,gate,details,candidates in variants:
            if {r['date'] for r in candidates}!=test_dates: raise ValueError('Meta gating dropped test date')
            case=dict(model=model,feature_set='causal_daily_gate',meta_threshold=gate,details=details,
                folds=[dict(test_first=min(test_dates),test_last=max(test_dates))],outcomes=[])
            for cost,delay in [(10,16),(20,16),(10,17)]:
                result=portfolio(candidates,market,.65,cost,delay)
                result['known_prefix_metrics']=accounting_metrics(dict(result,profit_usd=result['known_prefix_profit_usd']),candidates)
                result['known_prefix_cost_diagnostic']=diagnostic(dict(result,profit_usd=result['known_prefix_profit_usd']))
                check(result);case['outcomes'].append(result)
                print(json.dumps(dict(model=model,meta_gate=gate,cost=cost,delay=delay,active_days=result['active_days'],
                    win_rate=result['active_day_win_rate_pct'],net_usd=result['profit_usd'],
                    complete=result['full_period_coverage_complete'])),flush=True)
            report['cases'].append(case);(output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_causal_daily_gate'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--reference',type=Path,default=Path('research_runs/causal_sparse/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/causal_daily_gate'))
    a=p.parse_args();run(a.data,a.reference,a.output)
