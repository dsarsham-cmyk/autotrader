"""HINDSIGHT opportunity inventory, never a forecast or tradable oracle."""
import argparse
import hashlib
import json
from pathlib import Path
from balanced_target_simulator import path
from calendar_regular_context import calendar_lookup,clip_sessions
from causal_opening_inventory import load_observations
from causal_sparse_research import market_maps


def inventory(forecasts,market,target,cost=10,delay=16):
    grouped={};seen=set()
    for f in forecasts:
        key=(f['date'],f['symbol'])
        if key in seen: raise ValueError('Duplicate causal opening candidate')
        seen.add(key);grouped.setdefault(f['date'],[]).append(f)
    daily=[]
    for date,rows in sorted(grouped.items()):
        positive=[];negative=[];unknown=[];unfilled=[]
        for f in rows:
            o=path(market.get(date,{}).get(f['symbol'],{}),f['signal_price'],cost,delay,target)
            if o is None: unknown.append(f['symbol'])
            elif not o['filled']: unfilled.append(f['symbol'])
            elif o['label']:
                positive.append(dict(symbol=f['symbol'],net_return_fraction=o['exit']/o['entry']-1))
            else: negative.append(f['symbol'])
        daily.append(dict(date=date,candidates=len(rows),known_positive=positive,
            known_nonpositive=negative,known_unfilled=unfilled,unknown_paths=unknown))
    return dict(target_fraction=target,costs_bps=cost,delay=delay,sessions=len(daily),
        candidates=len(seen),known_positive_paths=sum(len(d['known_positive']) for d in daily),
        known_nonpositive_paths=sum(len(d['known_nonpositive']) for d in daily),
        known_unfilled_paths=sum(len(d['known_unfilled']) for d in daily),
        unknown_paths=sum(len(d['unknown_paths']) for d in daily),
        days_with_known_positive_path=sum(bool(d['known_positive']) for d in daily),
        days_without_known_positive_and_complete=sum(not d['known_positive'] and not d['unknown_paths'] for d in daily),
        days_without_known_positive_but_unknown=sum(not d['known_positive'] and bool(d['unknown_paths']) for d in daily),
        daily=daily,uses_future_outcomes=True,tradable=False,orders=False,
        target_screen_pass=False,independent_validation_pass=False,production_approved=False)


def capture(forecasts,opportunities):
    groups={}
    for f in forecasts: groups.setdefault(f['date'],[]).append(f)
    captured=available=selected_unknown=0;days=0
    for d in opportunities['daily']:
        positive={p['symbol'] for p in d['known_positive']}
        chosen={f['symbol'] for f in sorted(
            [f for f in groups[d['date']] if f['probability']>=.65],
            key=lambda f:(-f['probability'],f['symbol']))[:3]}
        hit=len(positive&chosen)
        captured+=hit;available+=len(positive);days+=bool(hit)
        selected_unknown+=len(chosen&set(d['unknown_paths']))
    return dict(selection_gate=.65,top_candidates=3,known_positive_paths_available=available,
        known_positive_paths_rank_selected=captured,days_rank_selecting_known_positive=days,
        selected_unknown_paths=selected_unknown,
        selection_recall_known_positive=captured/available if available else None,
        actual_executed_capture=False,
        limitation='Ranking before fill/sizing/portfolio guards; not executed P&L or winning-day rate')


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def run(data,study,output):
    reference=json.loads(study.read_bytes())
    if reference['status']!='completed_exposed_calendar_predictive_comparison': raise ValueError('Completed reference required')
    for name,expected in reference['source_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected:
            raise ValueError('Reference source changed')
    audit=Path('research_runs/calendar_regular_context/results.json')
    if sha(audit)!=reference['input_audit_sha256']: raise ValueError('Input audit changed')
    receipt=audit.parent/'calendar_receipt.json'
    if sha(receipt)!=json.loads(audit.read_bytes())['calendar_receipt_sha256']: raise ValueError('Calendar changed')
    observations,evidence=load_observations(data)
    if evidence!=reference['evidence']: raise ValueError('Historical input changed')
    market=market_maps(clip_sessions(observations,calendar_lookup(json.loads(receipt.read_bytes())['rows'])))
    results=[]
    for target in (.004,.01):
        cases=[c for c in reference['cases'] if c['target_fraction']==target]
        candidate=lambda c:{(f['date'],f['symbol']):f['signal_price'] for f in c['forecasts']}
        if len(cases)!=2 or candidate(cases[0])!=candidate(cases[1]): raise ValueError('Matched causal candidates required')
        for cost,delay in ((10,16),(20,16),(10,17)):
            result=inventory(cases[0]['forecasts'],market,target,cost,delay)
            if sum(result[k] for k in ['known_positive_paths','known_nonpositive_paths','known_unfilled_paths','unknown_paths'])!=result['candidates']:
                raise ValueError('Path reconciliation failed')
            result['model_selection']=[dict(model=c['model'],**capture(c['forecasts'],result)) for c in cases]
            results.append(result)
            print(json.dumps({k:result[k] for k in ['target_fraction','costs_bps','delay','sessions',
                'days_with_known_positive_path','days_without_known_positive_and_complete',
                'days_without_known_positive_but_unknown','known_positive_paths','unknown_paths','model_selection']}),flush=True)
    report=dict(status='completed_hindsight_net_opportunity_inventory_NOT_VALIDATION',cases=results,
        reference_sha256=sha(study),evidence=evidence,
        source_sha256={n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['net_opportunity_inventory.py','balanced_target_simulator.py']},
        uses_future_outcomes=True,tradable=False,orders=False,performance_screen_pass=False,
        independent_validation_pass=False,production_approved=False,
        limitations=['HINDSIGHT descriptive inventory, not a model, backtest success or independent validation',
            'Known profitable standalone path is NOT a risk-sized executable winning portfolio day',
            'No oracle dollar profit, cumulative capital, winning-day rate or automatic target qualification',
            'Unknown paths retained; no-known-positive is not certainly impossible when outcomes missing',
            'Fixed universe/entry/exit/cost assumptions only; not a mathematical upper bound on all strategies',
            'Future outcomes can diagnose missed opportunities but cannot be used as live signals'])
    output.mkdir(parents=True,exist_ok=True)
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--study',type=Path,default=Path('research_runs/calendar_predictive/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/net_opportunity_inventory'))
    a=p.parse_args();run(a.data,a.study,a.output)
