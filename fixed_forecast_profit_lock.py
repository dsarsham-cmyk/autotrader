"""Isolate modeled exit change, preserving forecasts and conservative risk replay."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from causal_opening_inventory import load_observations
from causal_sparse_research import market_maps
from profit_lock_simulator import path,portfolio
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic
from finbert_comparison_audit import check


def fixed_quantity_diagnostic(original,market):
    """Mechanical same-entry/quantity counterfactual, NOT a risk-approved replay."""
    if not original['full_period_coverage_complete']: raise ValueError('Complete reference ledger required')
    if any(t['reason']=='account_guard' for t in original['trades']):
        return dict(status='unavailable_aggregate_guard_context',net_usd=None,delta_usd=None,orders=False)
    days={d['date']:0. for d in original['daily']};unknown=[];paired=[]
    for trade in original['trades']:
        bars=market.get(trade['date'],{}).get(trade['symbol'],{})
        if 29 not in bars: raise ValueError('Reference signal price absent')
        candidate=path(bars,float(bars[29][3]),original['costs_bps'],original['delay'],True)
        if candidate is None:
            unknown.append(dict(date=trade['date'],symbol=trade['symbol']));continue
        if not candidate['filled'] or not math.isclose(candidate['entry'],trade['entry'],abs_tol=1e-9):
            raise ValueError('Matched entry changed')
        pnl=trade['quantity']*(candidate['exit']-trade['entry'])
        days[trade['date']]+=pnl
        paired.append(dict(date=trade['date'],symbol=trade['symbol'],quantity=trade['quantity'],
            original_pnl=trade['pnl'],protected_pnl=pnl,exit_minute=candidate['exit_minute'],
            reason=candidate['reason'],protection_updates=candidate['protection_updates']))
    if not math.isclose(sum(t['pnl'] for t in original['trades']),original['profit_usd'],abs_tol=1e-7):
        raise ValueError('Original trade net mismatch')
    complete=not unknown;net=sum(days.values()) if complete else None
    active=[d['date'] for d in original['daily'] if d['active']]
    wins=sum(days[d]>0 for d in active)
    return dict(status='completed_fixed_quantity_exit_diagnostic' if complete else 'unknown_counterfactual_prices',
        net_usd=net,delta_usd=net-original['profit_usd'] if complete else None,
        active_days=len(active),win_rate_pct=wins/len(active)*100 if active and complete else None,
        paired_trades=paired,unknown=unknown,risk_approved=False,production_approved=False,orders=False,
        limitations=['Same reference quantities may violate budgets on changed counterfactual capital',
            'Mechanical exit comparison only, not broker fills, prediction validation or an executable policy'])


def run(data,reference,output):
    raw=reference.read_bytes();original=json.loads(raw)
    if original['status']!='completed_exposed_causal_sparse_research': raise ValueError('Completed reference required')
    for name,expected in original['dependency_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected: raise ValueError('Reference source changed')
    observations,evidence=load_observations(data)
    if evidence!=original['evidence']: raise ValueError('Reference observations changed')
    market=market_maps(observations);output.mkdir(parents=True,exist_ok=True)
    report=dict(status='running_exposed_fixed_forecast_profit_lock',reference_sha256=hashlib.sha256(raw).hexdigest(),evidence=evidence,
        dependency_sha256=dict(original['dependency_sha256'],**{n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['fixed_forecast_profit_lock.py','profit_lock_simulator.py','finbert_comparison_audit.py']}),
        cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Frozen probabilities calibrated for original exit policy, not protected policy',
            'Matched proposals, not guaranteed equal final shares; risk replay sizes on own evolving capital',
            'Separate fixed-quantity diagnostic is NOT a risk-approved strategy',
            'Exposed outcomes/modeled prices/replacements and fixed universe remain unvalidated independently'])
    for protect in [False,True]:
        for old in original['cases']:
            forecasts=old['forecasts'];case=dict(model=old['model'],feature_set='frozen_forecast_profit_lock' if protect else 'fixed_stop',
                folds=old['folds'],outcomes=[])
            for expected in old['outcomes']:
                gate,cost,delay=expected['threshold'],expected['costs_bps'],expected['delay']
                result=portfolio(forecasts,market,gate,cost,delay,protect)
                result['known_prefix_metrics']=accounting_metrics(dict(result,profit_usd=result['known_prefix_profit_usd']),forecasts)
                result['known_prefix_cost_diagnostic']=diagnostic(dict(result,profit_usd=result['known_prefix_profit_usd']))
                check(result)
                if not protect and any(result[k]!=expected[k] for k in ['daily','trades','profit_usd','unknown_selections']):
                    raise ValueError('Original forecast policy not reproduced')
                if protect: result['fixed_quantity_exit_diagnostic']=fixed_quantity_diagnostic(expected,market)
                case['outcomes'].append(result)
                if cost==10 and delay==16:
                    print(json.dumps(dict(protect=protect,model=old['model'],gate=gate,active_days=result['active_days'],
                        net_usd=result['profit_usd'],win_rate=result['active_day_win_rate_pct'],complete=result['full_period_coverage_complete'],
                        fixed_quantity_delta=result.get('fixed_quantity_exit_diagnostic',{}).get('delta_usd'))),flush=True)
            report['cases'].append(case);(output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_fixed_forecast_profit_lock'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--reference',type=Path,default=Path('research_runs/causal_sparse/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/fixed_forecast_profit_lock'))
    a=p.parse_args();run(a.data,a.reference,a.output)
