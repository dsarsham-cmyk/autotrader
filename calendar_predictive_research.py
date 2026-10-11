"""Re-fit own past labels on calendar-correct inputs; exposed research only."""
import argparse
import hashlib
import json
from pathlib import Path
from threadpoolctl import threadpool_limits
from balanced_target_research import walk
from balanced_target_simulator import portfolio
from calendar_regular_context import calendar_lookup,calendar_opening_rows,clip_sessions
from causal_opening_inventory import load_observations
from causal_sparse_research import market_maps
from finbert_comparison_audit import check
from prospective_series_audit import accounting_metrics
from research_calendar_audit import inspect as inspect_calendar
from split_context_audit import events_from_pages
from split_predictive_research import flatten


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(data,audit,reference,output):
    input_report=json.loads(audit.read_bytes())
    old=json.loads(reference.read_bytes())
    if input_report['status']!='exposed_historical_calendar_input_audit' or not input_report['normal_close_control_exact']:
        raise ValueError('Completed exact-control calendar input audit required')
    if old['status']!='completed_exposed_balanced_target_comparison':
        raise ValueError('Completed matched-target reference required')
    for name,expected in dict(old['dependency_sha256'],**input_report['source_sha256']).items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected:
            raise ValueError('Study dependency changed')
    receipt=audit.parent/'calendar_receipt.json'
    split=Path('research_runs/split_context_audit/corporate_actions_receipt.json')
    if sha(receipt)!=input_report['calendar_receipt_sha256'] or sha(split)!=input_report['split_receipt_sha256']:
        raise ValueError('Input receipt changed')
    observations,evidence=load_observations(data)
    if evidence!=input_report['evidence'] or evidence!=old['evidence']:
        raise ValueError('Historical inputs changed')
    cal=calendar_lookup(json.loads(receipt.read_bytes())['rows'])
    events=events_from_pages(json.loads(split.read_bytes())['pages'],list(observations))
    rows=flatten(calendar_opening_rows(observations,events,cal)[0])
    market=market_maps(clip_sessions(observations,cal))
    output.mkdir(parents=True,exist_ok=True)
    report=dict(status='running_exposed_calendar_predictive_comparison',cases=[],evidence=evidence,
        input_audit_sha256=sha(audit),reference_sha256=sha(reference),
        source_sha256={name:hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for name in ['calendar_predictive_research.py','calendar_regular_context.py',
                         'balanced_target_research.py','balanced_target_simulator.py','research_calendar_audit.py']},
        protocol=old['protocol'],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Retrospective exposed inputs, not independent forward evidence',
            'Re-fit both models with their own past labels; no transfer of old probabilities',
            'Same stops, sizing, budgets, costs, latency and horizons; no production mutation',
            'Correct calendar does not prove original data delivery or real execution'])
    with threadpool_limits(limits=1):
        for target in (.004,.01):
            for model in ('logistic','boosted'):
                forecasts,folds=walk(rows,market,model,target)
                baseline=next(c for c in old['cases'] if c['model']==model and c['target_fraction']==target)
                same_span=[(f['test_first'],f['test_last']) for f in folds]==[
                    (f['test_first'],f['test_last']) for f in baseline['folds']]
                case=dict(model=model,target_fraction=target,folds=folds,forecasts=forecasts,
                          reference_fold_dates_equal=same_span,outcomes=[])
                for gate in (.5,.65,.9):
                    for cost,delay in ((10,16),(20,16),(10,17)):
                        result=portfolio(forecasts,market,gate,cost,delay,target)
                        result['known_prefix_metrics']=accounting_metrics(
                            dict(result,profit_usd=result['known_prefix_profit_usd']),forecasts)
                        if not check(result): raise ValueError('Reported budget/risk invariant failed')
                        prior=next(o for o in baseline['outcomes'] if
                            (o['threshold'],o['costs_bps'],o['delay'])==(gate,cost,delay))
                        result['reference_net_usd']=prior['profit_usd']
                        result['net_change_usd']=(result['profit_usd']-prior['profit_usd']
                            if result['profit_usd'] is not None and prior['profit_usd'] is not None else None)
                        case['outcomes'].append(result)
                        if cost==10 and delay==16:
                            print(json.dumps(dict(model=model,target=target,gate=gate,
                                active_days=result['active_days'],win_rate=result['active_day_win_rate_pct'],
                                net_usd=result['profit_usd'],net_change=result['net_change_usd'],
                                complete=result['full_period_coverage_complete'])),flush=True)
                report['cases'].append(case)
                (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_calendar_predictive_comparison'
    report['calendar_coverage']=inspect_calendar(report,
        {r['date']:r for r in json.loads(receipt.read_bytes())['rows']})
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--audit',type=Path,default=Path('research_runs/calendar_regular_context/results.json'))
    p.add_argument('--reference',type=Path,default=Path('research_runs/balanced_target/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/calendar_predictive'))
    a=p.parse_args();run(a.data,a.audit,a.reference,a.output)
