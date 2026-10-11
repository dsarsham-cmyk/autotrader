"""Describe exposed forecast reliability; no fitting, gating changes or orders."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from balanced_target_simulator import path
from calendar_regular_context import calendar_lookup,clip_sessions
from causal_opening_inventory import load_observations
from causal_sparse_research import market_maps
from predictive_research import wilson

EDGES=(0.,.5,.65,.8,.9,1.)


def summarize(records):
    seen=set()
    for r in records:
        key=(r['date'],r['symbol'])
        p=r['probability']
        if key in seen or isinstance(p,bool) or not math.isfinite(p) or not 0<=p<=1:
            raise ValueError('Invalid or duplicate probability')
        if isinstance(r['label'],bool) or r['label'] not in (0,1): raise ValueError('Binary outcome required')
        seen.add(key)
    count=len(records)
    bins=[]
    for lo,hi in zip(EDGES[:-1],EDGES[1:]):
        group=[r for r in records if lo<=r['probability'] and
               (r['probability']<hi or hi==1 and r['probability']==1)]
        wins=sum(r['label'] for r in group)
        n=len(group)
        mean=sum(r['probability'] for r in group)/n if n else None
        observed=wins/n if n else None
        bins.append(dict(lower=lo,upper=hi,upper_inclusive=hi==1,count=n,
            distinct_days=len({r['date'] for r in group}),mean_probability=mean,
            observed_positive_fraction=observed,positive_outcomes=wins,
            probability_minus_observed=mean-observed if n else None,
            descriptive_wilson_pct=wilson(wins,n)))
    if sum(b['count'] for b in bins)!=count: raise ValueError('Bin reconciliation failed')
    return dict(count=count,distinct_days=len({r['date'] for r in records}),bins=bins,
        brier=sum((r['probability']-r['label'])**2 for r in records)/count if count else None,
        observed_positive_fraction=sum(r['label'] for r in records)/count if count else None,
        expected_calibration_error=sum(b['count']*abs(b['probability_minus_observed'])
            for b in bins if b['count'])/count if count else None,
        independent_validation_pass=False)


def inspect_case(case,market):
    records=[];unknown=[];unfilled=0;index={}
    for f in case['forecasts']:
        key=(f['date'],f['symbol'])
        if key in index: raise ValueError('Duplicate forecast')
        index[key]=f
        o=path(market.get(f['date'],{}).get(f['symbol'],{}),f['signal_price'],
               target_fraction=case['target_fraction'])
        if o is None: unknown.append(dict(date=f['date'],symbol=f['symbol']))
        elif not o['filled']: unfilled+=1
        else: records.append(dict(date=f['date'],symbol=f['symbol'],
                                  probability=f['probability'],label=o['label']))
    actual=next(o for o in case['outcomes'] if
        (o['threshold'],o['costs_bps'],o['delay'])==(.65,10,16))
    executed=[]
    for t in actual['trades']:
        f=index[(t['date'],t['symbol'])]
        executed.append(dict(date=t['date'],symbol=t['symbol'],probability=f['probability'],label=int(t['pnl']>0)))
    return dict(model=case['model'],target_fraction=case['target_fraction'],
        forecast_candidates=len(index),known_unfilled=unfilled,unknown_paths=unknown,
        standalone_known_filled=summarize(records),executed_primary_gate065=summarize(executed),
        execution_ledger_complete=actual['full_period_coverage_complete'],
        primary_net_usd=actual['profit_usd'],primary_active_days=actual['active_days'],
        primary_active_day_win_pct=actual['active_day_win_rate_pct'])


def run(data,study,output):
    report=json.loads(study.read_bytes())
    if report['status']!='completed_exposed_calendar_predictive_comparison':
        raise ValueError('Completed corrected-calendar study required')
    for name,expected in report['source_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected:
            raise ValueError('Study source changed')
    audit=Path('research_runs/calendar_regular_context/results.json')
    if hashlib.sha256(audit.read_bytes()).hexdigest()!=report['input_audit_sha256']:
        raise ValueError('Input audit changed')
    input_report=json.loads(audit.read_bytes())
    receipt=audit.parent/'calendar_receipt.json'
    if hashlib.sha256(receipt.read_bytes()).hexdigest()!=input_report['calendar_receipt_sha256']:
        raise ValueError('Calendar receipt changed')
    observations,evidence=load_observations(data)
    if evidence!=report['evidence']: raise ValueError('Historical observations changed')
    market=market_maps(clip_sessions(observations,calendar_lookup(json.loads(receipt.read_bytes())['rows'])))
    cases=[inspect_case(c,market) for c in report['cases']]
    result=dict(status='completed_exposed_forecast_reliability_audit',cases=cases,
        study_sha256=hashlib.sha256(study.read_bytes()).hexdigest(),
        source_sha256={n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['forecast_reliability_audit.py','balanced_target_simulator.py','predictive_research.py']},
        orders=False,production_approved=False,performance_screen_pass=False,independent_validation_pass=False,
        limitations=['Descriptive exposed walk-forward audit, not new independent evidence',
            'Standalone label is profitable net path conditional on fill, not winning portfolio day',
            'Executed subset is selected and includes portfolio guards; not an unbiased calibration population',
            'Fixed probability bins are descriptive; no recalibration, threshold tuning or model promotion',
            'Stocks and days correlated; Wilson bounds are not certified independent confidence',
            'Missing paths are reported separately; known-only statistics do not impute unknown outcomes'])
    output.mkdir(parents=True,exist_ok=True)
    (output/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    for c in cases:
        print(json.dumps(dict(model=c['model'],target=c['target_fraction'],
            known_filled=c['standalone_known_filled']['count'],unknown=len(c['unknown_paths']),
            brier=c['standalone_known_filled']['brier'],
            bins=c['standalone_known_filled']['bins'])),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--study',type=Path,default=Path('research_runs/calendar_predictive/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/forecast_reliability'))
    a=p.parse_args();run(a.data,a.study,a.output)
