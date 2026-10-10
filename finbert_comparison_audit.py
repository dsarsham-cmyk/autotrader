"""Reconcile the predeclared matched sentiment study, never approve trading."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from research_calendar_audit import calendar_dates,inspect
from predictive_research import wilson

ARMS=['headline_events','headline_events_plus_finbert']
MODELS=['logistic','boosted']
AXES={(gate,cost,delay) for gate in [.5,.65,.9] for cost,delay in [(10,16),(20,16),(10,17)]}
RISK=['category_budget_pass','stock_budget_pass','max_positions_pass','planned_risk_pass']


def check(outcome):
    if any(outcome[k] for k in ['orders','production_approved','independent_validation_pass']):
        raise ValueError('Unauthorized approval/order flag')
    daily=outcome['daily'];dates=[d['date'] for d in daily]
    if dates!=sorted(set(dates)): raise ValueError('Duplicate or unordered ledger dates')
    trades=outcome['trades']
    if any(t['date'] not in dates for t in trades): raise ValueError('Trade outside ledger')
    equity=100000.
    for day in daily:
        values=[t['pnl'] for t in trades if t['date']==day['date']]
        if bool(values)!=day['active'] or not math.isclose(sum(values),day['pnl'],abs_tol=1e-7):
            raise ValueError('Trade/day reconciliation failed')
        equity+=day['pnl']
        if not math.isclose(equity,day['equity'],abs_tol=1e-7): raise ValueError('Equity mismatch')
    if not math.isclose(equity-100000.,outcome['known_prefix_profit_usd'],abs_tol=1e-7):
        raise ValueError('Prefix profit mismatch')
    active=sum(d['active'] for d in daily)
    if active!=outcome['active_days']: raise ValueError('Active day mismatch')
    if outcome['full_period_coverage_complete']:
        if outcome['unknown_selections'] or len(daily)!=outcome['expected_forecast_sessions']:
            raise ValueError('False complete coverage')
        if not math.isclose(equity-100000.,outcome['profit_usd'],abs_tol=1e-7): raise ValueError('Net mismatch')
        wins=sum(d['active'] and d['pnl']>0 for d in daily)
        rate=wins/active*100 if active else None
        observed=outcome['active_day_win_rate_pct']
        if (rate is None and observed is not None) or (rate is not None and
                (observed is None or not math.isclose(rate,observed,abs_tol=1e-10))):
            raise ValueError('Win rate mismatch')
        screen=bool(active>=100 and wilson(wins,active)[0]>=90 and equity>100000.)
        if bool(outcome['target_screen_pass'])!=screen: raise ValueError('Target screen mismatch')
    elif outcome['profit_usd'] is not None or outcome['active_day_win_rate_pct'] is not None:
        raise ValueError('Unknown outcomes presented as full-period performance')
    elif outcome['target_screen_pass']:
        raise ValueError('Incomplete outcomes pass target screen')
    return all(outcome['known_prefix_metrics'][k] for k in RISK)


def audit(report,calendar):
    if report['status']!='completed_exposed_finbert_input_ablation': raise ValueError('Completed comparison required')
    if any(report[k] for k in ['orders','production_approved','independent_validation_pass']):
        raise ValueError('Unauthorized study flag')
    indexed={}
    for case in report['cases']:
        key=(case['feature_set'],case['model'])
        if key in indexed: raise ValueError('Duplicate study case')
        outcomes={}
        for o in case['outcomes']:
            axis=(o['threshold'],o['costs_bps'],o['delay'])
            if axis in outcomes: raise ValueError('Duplicate variant')
            check(o);outcomes[axis]=o
        if set(outcomes)!=AXES: raise ValueError('Missing or unexpected predeclared variant')
        indexed[key]=outcomes
    if set(indexed)!={(a,m) for a in ARMS for m in MODELS}: raise ValueError('Missing or unexpected study case')
    coverage=inspect(report,calendar);pairs=[]
    for model in MODELS:
        for axis in sorted(AXES):
            before=indexed[(ARMS[0],model)][axis];after=indexed[(ARMS[1],model)][axis]
            complete=before['full_period_coverage_complete'] and after['full_period_coverage_complete']
            if complete and [d['date'] for d in before['daily']]!=[d['date'] for d in after['daily']]:
                raise ValueError('Unmatched comparison dates')
            pairs.append(dict(model=model,threshold=axis[0],costs_bps=axis[1],delay=axis[2],
                both_full_period=complete,
                net_delta_usd=after['profit_usd']-before['profit_usd'] if complete else None,
                baseline_net_usd=before['profit_usd'],sentiment_net_usd=after['profit_usd'],
                baseline_active_days=before['active_days'],sentiment_active_days=after['active_days'],
                baseline_win_rate=before['active_day_win_rate_pct'],sentiment_win_rate=after['active_day_win_rate_pct']))
    return dict(status='completed_retrospective_matched_finbert_audit',paired_variants=pairs,
        calendar_audit=coverage,all_reported_risk_checks_pass=all(check(o) for v in indexed.values() for o in v.values()),
        passing_target_screens=sum(o['target_screen_pass'] for v in indexed.values() for o in v.values()),
        orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Ledger reconciliation is not independent fill or risk-model reproduction',
            'Paired differences on exposed historical outcomes are exploratory, not proof of an advantage',
            'Active/no-trade days cannot be relabeled as winning days; no automatic promotion'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,default=Path('research_runs/finbert_ablation/results.json'))
    p.add_argument('--calendar',type=Path,required=True)
    p.add_argument('--output',type=Path,default=Path('research_runs/finbert_comparison_audit/results.json'))
    a=p.parse_args();raw=a.input.read_bytes();receipt=a.calendar.read_bytes();c=json.loads(receipt)
    result=audit(json.loads(raw),calendar_dates(c['calendar'],c['start'],c['end']))
    result.update(input_sha256=hashlib.sha256(raw).hexdigest(),calendar_sha256=hashlib.sha256(receipt).hexdigest(),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest())
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps(dict(passing_target_screens=result['passing_target_screens'],pairs=len(result['paired_variants']),
        calendar_complete=result['calendar_audit']['all_observed_spans_cover_calendar'],orders=False)))
