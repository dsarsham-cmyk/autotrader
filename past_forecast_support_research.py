"""Past forecast-day support gate; statistical screen, not a guarantee.

Reference days are ungated counterfactual controls, not the gated trader's
realized history. Complete date-grouped ledgers prevent missing-day cherry-picks.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
from causal_opening_inventory import load_observations
from causal_sparse_research import market_maps
from causal_sparse_simulator import portfolio
from finbert_comparison_audit import check
from fixed_trade_cost_diagnostic import diagnostic
from predictive_research import wilson
from prospective_series_audit import accounting_metrics
from split_predictive_research import assert_reference


def support_schedule(dates, daily, gate, lookback=60, minimum_active=20):
    if not 0<=gate<=1 or lookback<1 or not 1<=minimum_active<=lookback:
        raise ValueError('Invalid support protocol')
    if dates!=sorted(set(dates)) or [d['date'] for d in daily]!=dates:
        raise ValueError('Complete chronological control dates required')
    for d in daily:
        if type(d['active']) is not bool or not math.isfinite(d['pnl']) or (not d['active'] and d['pnl']!=0):
            raise ValueError('Invalid control daily accounting')
    schedule=[]
    for i,date in enumerate(dates):
        window=daily[max(0,i-lookback):i]  # Excludes current and all future outcomes.
        active=[d for d in window if d['active']]
        wins=sum(d['pnl']>0 for d in active)
        lower=wilson(wins,len(active))[0]/100 if active else None
        net=sum(d['pnl'] for d in window)
        permitted=(len(window)==lookback and len(active)>=minimum_active and lower>=gate and net>0)
        schedule.append(dict(date=date,past_first=window[0]['date'] if window else None,
            past_last=window[-1]['date'] if window else None,past_control_sessions=len(window),
            past_control_active_days=len(active),past_control_winning_days=wins,
            past_control_wilson_lower=lower,past_control_net_usd=net,trading_eligible=bool(permitted)))
    return schedule


def apply_support(forecasts, schedule):
    permissions={s['date']:s['trading_eligible'] for s in schedule}
    if len(permissions)!=len(schedule) or set(permissions)!={r['date'] for r in forecasts}:
        raise ValueError('Unique full-span permission schedule required')
    return [dict(r,forecast_probability=r['probability'],trading_eligible=permissions[r['date']],
                 probability=r['probability'] if permissions[r['date']] else 0.) for r in forecasts]


def run(data, reference, output):
    original=json.loads(reference.read_bytes())
    if original['status']!='completed_exposed_split_predictive_comparison': raise ValueError('Completed reference required')
    for name,expected in original['dependency_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected:
            raise ValueError('Reference source changed')
    observations,evidence=load_observations(data)
    if evidence!=original['evidence']: raise ValueError('Historical input bytes changed')
    market=market_maps(observations);output.mkdir(parents=True,exist_ok=True)
    report=dict(status='running_exposed_past_forecast_support',cases=[],evidence=evidence,
        reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        dependency_sha256=dict(original['dependency_sha256'],**{n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['past_forecast_support_research.py','finbert_comparison_audit.py']}),
        protocol=dict(lookback_forecast_sessions=60,minimum_active_control_days=20,
            requirement='positive past control net AND Wilson lower bound >= original probability gate',
            thresholds=[.5,.65,.9],cost_delay_variants=[(10,16),(20,16),(10,17)],orders=False),
        orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Exposed retrospective control forecasts reused, not new independent observations or model fitting',
            'Reference control is ungated counterfactual history, not gated realized profit or live trading',
            'Wilson assumes Bernoulli independence; correlated financial days invalidate guaranteed coverage',
            'Rolling windows and multiple variants overlap; neither selective nor multiple-testing guarantee',
            'Zero means denied permission, not predicted probability; original forecast_probability preserved',
            'Warmup abstention and no-trade days are not wins; fixed budgets/costs/execution assumptions unchanged'])
    for model in ['logistic','boosted']:
        old=next(c for c in original['cases'] if c['feature_set']=='date_effective_split_context' and c['model']==model)
        forecasts=old['forecasts'];dates=sorted({r['date'] for r in forecasts})
        for selector in ['probability_only','past_forecast_day_support']:
            case=dict(model=model,selector=selector,folds=old['folds'],forecasts=forecasts,outcomes=[])
            for gate in [.5,.65,.9]:
                for cost,delay in [(10,16),(20,16),(10,17)]:
                    expected=next(o for o in old['outcomes'] if (o['threshold'],o['costs_bps'],o['delay'])==(gate,cost,delay))
                    if not expected['full_period_coverage_complete']: raise ValueError('Incomplete control cannot support screen')
                    schedule=support_schedule(dates,expected['daily'],gate)
                    selected=forecasts if selector=='probability_only' else apply_support(forecasts,schedule)
                    result=portfolio(selected,market,gate,cost,delay)
                    result.update(selector=selector,permission_gate_applied=selector!='probability_only')
                    if selector!='probability_only':
                        result.update(support_schedule=schedule,eligible_forecast_days=sum(s['trading_eligible'] for s in schedule))
                    prefix=dict(result,profit_usd=result['known_prefix_profit_usd'])
                    result['known_prefix_metrics']=accounting_metrics(prefix,selected)
                    result['known_prefix_cost_diagnostic']=diagnostic(prefix)
                    check(result)
                    if selector=='probability_only': assert_reference(result,expected)
                    case['outcomes'].append(result)
                    if cost==10 and delay==16:
                        print(json.dumps(dict(model=model,selector=selector,gate=gate,
                            active_days=result['active_days'],win_rate=result['active_day_win_rate_pct'],
                            net_usd=result['profit_usd'],eligible_days=result.get('eligible_forecast_days'))),flush=True)
            report['cases'].append(case)
            (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_past_forecast_support'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--reference',type=Path,default=Path('research_runs/split_predictive/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/past_forecast_support'))
    a=p.parse_args();run(a.data,a.reference,a.output)
