"""Reproduce filtered ledgers and compare matched predecision controls only."""
import argparse
import hashlib
import json
from pathlib import Path
from balanced_target_simulator import portfolio
from calendar_regular_context import calendar_lookup,clip_sessions
from causal_opening_inventory import load_observations
from causal_sparse_research import market_maps
from finbert_comparison_audit import check
from portfolio_day_research import apply_permission
from prospective_series_audit import accounting_metrics
from research_calendar_audit import inspect as calendar_audit
from split_predictive_research import assert_reference


def control_schedule(decisions,kind):
    dates=[d['date'] for d in decisions]
    if dates!=sorted(set(dates)): raise ValueError('Unique chronological decisions required')
    if kind not in ('warmup_only','past_support_matched'): raise ValueError('Unknown control')
    return [dict(date=d['date'],day_probability=1. if (
        i>=90 if kind=='warmup_only' else d['day_probability'] is not None) else None)
        for i,d in enumerate(decisions)]


def compare(filtered,control):
    if [d['date'] for d in filtered['daily']]!=[d['date'] for d in control['daily']]:
        raise ValueError('Complete matched ledger dates required')
    both=filtered['full_period_coverage_complete'] and control['full_period_coverage_complete']
    average=lambda o:o['profit_usd']/o['active_days'] if o['profit_usd'] is not None and o['active_days'] else None
    return dict(both_full_period_complete=both,filtered_net_usd=filtered['profit_usd'],
        control_net_usd=control['profit_usd'],net_delta_usd=filtered['profit_usd']-control['profit_usd'] if both else None,
        filtered_active_days=filtered['active_days'],control_active_days=control['active_days'],
        filtered_win_pct=filtered['active_day_win_rate_pct'],control_win_pct=control['active_day_win_rate_pct'],
        filtered_mean_net_per_active_day=average(filtered),control_mean_net_per_active_day=average(control),
        independent_validation_pass=False,
        limitation='Descriptive matched-control difference; fewer trades or smaller total loss is not proof of predictive edge')


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def run(data,filtered_path,reference,output):
    filtered=json.loads(filtered_path.read_bytes());base=json.loads(reference.read_bytes())
    if filtered['status']!='completed_exposed_portfolio_day_comparison' or base['status']!='completed_exposed_calendar_predictive_comparison':
        raise ValueError('Completed inputs required')
    if sha(reference)!=filtered['reference_sha256']: raise ValueError('Reference changed')
    for n,h in dict(base['source_sha256'],**filtered['source_sha256']).items():
        if hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=h: raise ValueError('Input source changed')
    audit=Path('research_runs/calendar_regular_context/results.json')
    if sha(audit)!=base['input_audit_sha256']: raise ValueError('Input audit changed')
    receipt=audit.parent/'calendar_receipt.json'
    if sha(receipt)!=json.loads(audit.read_bytes())['calendar_receipt_sha256']: raise ValueError('Calendar changed')
    observations,evidence=load_observations(data)
    if evidence!=filtered['evidence'] or evidence!=base['evidence']: raise ValueError('Historical inputs changed')
    market=market_maps(clip_sessions(observations,calendar_lookup(json.loads(receipt.read_bytes())['rows'])))
    output.mkdir(parents=True,exist_ok=True)
    report=dict(status='running_exposed_portfolio_day_matched_audit',cases=[],pairs=[],
        filtered_sha256=sha(filtered_path),reference_sha256=sha(reference),evidence=evidence,
        source_sha256={n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['portfolio_day_matched_audit.py','portfolio_day_research.py','balanced_target_simulator.py']},
        orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Same initial capital and full429-date ledger; no daily reset or future outcome filters',
            'Warmup-only control skips90 dates; support-matched control also skips insufficient past label support',
            'Controls change permission only, keep original stock ranking and all risk/execution assumptions',
            'Cumulative capital diverges by policy; do not assert exact matched quantities',
            'Filtered ledgers reproduced exactly; differences are exposed descriptive comparisons, not independent proof'])
    for old in base['cases']:
        candidates=[c for c in filtered['cases'] if (c['model'],c['target_fraction'])==(old['model'],old['target_fraction'])]
        if len(candidates)!=2 or sorted(c['day_gate'] for c in candidates)!=[.65,.9]: raise ValueError('Both fixed day gates required')
        decisions=candidates[0]['day_schedule']
        if decisions!=candidates[1]['day_schedule']: raise ValueError('Unmatched day forecast schedule')
        # The filtered artifacts cannot silently substitute original scores/prices.
        for case in candidates:
            expected=apply_permission(old['forecasts'],decisions,case['day_gate'])
            if expected!=case['forecasts']: raise ValueError('Filtered candidate inputs changed')
            for original in case['outcomes']:
                reproduced=portfolio(expected,market,.65,original['costs_bps'],original['delay'],old['target_fraction'])
                assert_reference(reproduced,original)
        for kind in ('warmup_only','past_support_matched'):
            selected=apply_permission(old['forecasts'],control_schedule(decisions,kind),.65)
            control=dict(model=old['model'],target_fraction=old['target_fraction'],control=kind,folds=old['folds'],outcomes=[])
            for cost,delay in ((10,16),(20,16),(10,17)):
                outcome=portfolio(selected,market,.65,cost,delay,old['target_fraction'])
                outcome['known_prefix_metrics']=accounting_metrics(dict(outcome,profit_usd=outcome['known_prefix_profit_usd']),selected)
                if not check(outcome): raise ValueError('Control risk/budget invariant failed')
                control['outcomes'].append(outcome)
                for case in candidates:
                    actual=next(o for o in case['outcomes'] if (o['costs_bps'],o['delay'])==(cost,delay))
                    pair=dict(model=old['model'],target_fraction=old['target_fraction'],day_gate=case['day_gate'],
                        control=kind,costs_bps=cost,delay=delay,**compare(actual,outcome))
                    report['pairs'].append(pair)
                    if cost==10 and delay==16 and kind=='past_support_matched': print(json.dumps(pair),flush=True)
            report['cases'].append(control)
            (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_portfolio_day_matched_audit'
    report['all_filtered_ledgers_reproduced_exactly']=True
    report['calendar_coverage']=calendar_audit(report,{r['date']:r for r in json.loads(receipt.read_bytes())['rows']})
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--filtered',type=Path,default=Path('research_runs/portfolio_day/results.json'))
    p.add_argument('--reference',type=Path,default=Path('research_runs/calendar_predictive/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/portfolio_day_matched'))
    a=p.parse_args();run(a.data,a.filtered,a.reference,a.output)
