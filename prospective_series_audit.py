"""Read-only cumulative evaluation of the fixed prospective research control.

Market/session gaps are not no-trade days. This is an OHLC virtual sleeve,
never broker execution, live-trading approval or a promise of daily income.
"""
import argparse
from datetime import datetime,time,timedelta,timezone
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from dotenv import load_dotenv

from prospective_full_audit import load_verified_sessions,get_json
from prospective_forecast_evidence import read_manifest
from prospective_outcome_audit import evaluate_simulated_session,save_once_or_identical
from predictive_portfolio_research import portfolio,path_outcome
from fixed_trade_cost_diagnostic import diagnostic

INITIAL=100000.
VARIANTS=[(10,16),(20,16),(10,17)]


def completed_calendar(envelope,work,now=None):
    """Record all completed exchange sessions, including unsupported half-days."""
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None: raise ValueError('Aware audit clock required')
    first=envelope['manifest']['forward_start']
    last=str(now.astimezone(ZoneInfo('America/New_York')).date())
    raw=[] if first>last else get_json('https://paper-api.alpaca.markets/v2/calendar',
        {'start':first,'end':last})
    if not isinstance(raw,list): raise ValueError('Calendar response must be a list')
    dates=[];unsupported=[];seen=set()
    for row in raw:
        date=row['date']
        if date in seen or not first<=date<=last: raise ValueError('Duplicate/out-of-range calendar session')
        seen.add(date)
        close=datetime.combine(datetime.fromisoformat(date).date(),time.fromisoformat(row['close']),
            ZoneInfo('America/New_York'))
        if close+timedelta(minutes=16)>now: continue
        dates.append(date)
        if row['open']!='09:30' or row['close']!='16:00': unsupported.append(date)
    encoded=json.dumps(dict(retrieved_utc=now.isoformat(),calendar=raw),sort_keys=True,
        separators=(',',':'),allow_nan=False).encode()
    name=hashlib.sha256(encoded).hexdigest()
    save_once_or_identical(work/'calendar'/f'{name}.json',encoded)
    return dict(completed_sessions=sorted(dates),unsupported_sessions=sorted(unsupported),
        receipt_sha256=name,retrieved_utc=now.isoformat())


def accounting_metrics(outcome,rows):
    """Reconcile cash sizing and drawdown without inventing intraday peaks."""
    equity=peak=INITIAL;max_drawdown=low_vs_eod_peak=0.;loss_streak=longest_loss_streak=0
    category=stock=positions=planned_risk=True
    by_key={(row['date'],row['symbol']):row for row in rows}
    for day in outcome['daily']:
        start=equity
        if not math.isclose(start+day['pnl'],day['equity'],abs_tol=1e-7):
            raise ValueError('Cumulative capital/accounting mismatch')
        category &= day['committed_usd']<=start*.05+1e-7
        trades=[trade for trade in outcome['trades'] if trade['date']==day['date']]
        positions &= len(trades)<=3 and len({t['symbol'] for t in trades})==len(trades)
        committed=0.
        for trade in trades:
            row=by_key[(day['date'],trade['symbol'])]
            reserved=trade['quantity']*row['signal_price']*1.001
            committed+=reserved
            stock &= reserved<=start*.01+1e-7
            cost=trade['per_side_cost_bps']/10000
            risk=trade['quantity']*(trade['entry']-trade['raw_entry']*.99*(1-cost))
            planned_risk &= risk<=start*.0005+1e-7
        if not math.isclose(committed,day['committed_usd'],abs_tol=1e-7):
            raise ValueError('Committed capital mismatch')
        low=start*(1+day['worst_marked_pct']/100)
        low_vs_eod_peak=max(low_vs_eod_peak,1-low/peak)
        equity=day['equity'];peak=max(peak,equity)
        max_drawdown=max(max_drawdown,1-equity/peak)
        loss_streak=loss_streak+1 if day['pnl']<0 else 0
        longest_loss_streak=max(longest_loss_streak,loss_streak)
    if not math.isclose(equity-INITIAL,outcome['profit_usd'],abs_tol=1e-7):
        raise ValueError('Final cumulative result mismatch')
    return dict(initial_virtual_equity=INITIAL,final_virtual_equity=equity,
        end_of_day_max_drawdown_pct=100*max_drawdown,
        conservative_low_mark_vs_prior_eod_peak_pct=100*low_vs_eod_peak,
        longest_consecutive_losing_observed_sessions=longest_loss_streak,
        winning_active_days=sum(d['active'] and d['pnl']>0 for d in outcome['daily']),
        losing_active_days=sum(d['active'] and d['pnl']<0 for d in outcome['daily']),
        flat_active_days=sum(d['active'] and d['pnl']==0 for d in outcome['daily']),
        category_budget_pass=bool(category),stock_budget_pass=bool(stock),
        max_positions_pass=bool(positions),planned_risk_pass=bool(planned_risk))


def probability_diagnostic(rows,by_date):
    # Labels are conditional on modeled fills, matching the frozen calibration.
    # Correlated stocks are NOT treated as independent winning trading days.
    pairs=[]
    for row in rows:
        outcome=path_outcome(by_date[row['date']][row['symbol']][0],row['signal_price'],
            30,'target_60',10,16)
        if outcome['filled']: pairs.append((row['probability'],outcome['label']))
    bins=[]
    for lo,hi in [(0,.5),(.5,.65),(.65,.8),(.8,.9),(.9,1.0000001)]:
        subset=[(p,y) for p,y in pairs if lo<=p<hi]
        bins.append(dict(probability_lower=lo,probability_upper=min(hi,1),filled_candidates=len(subset),
            mean_probability=float(np.mean([p for p,y in subset])) if subset else None,
            observed_positive_net_fraction=float(np.mean([y for p,y in subset])) if subset else None))
    return dict(mode='all_candidates_conditional_on_simulated_fill',filled_candidates=len(pairs),
        brier=float(np.mean([(p-y)**2 for p,y in pairs])) if pairs else None,bins=bins,
        note='Stock rows are correlated, not independent day observations; costs/fills are assumed')


def simulate_series(bundles,envelope,expected_sessions):
    """Pure evaluator. Supplying fixtures is NEVER proof of provenance."""
    if len(expected_sessions)!=len(set(expected_sessions)):
        raise ValueError('Duplicate expected market session')
    expected=set(expected_sessions);by_date={};rows=[];receipts=[]
    for bundle in bundles:
        packet=bundle['packet'];date=packet['record']['session_date']
        if date in by_date: raise ValueError('Duplicate session cannot increase sample size')
        if date not in expected: raise ValueError('Forecast not in completed calendar')
        if bundle.get('input_predictions_reproduced') is not True:
            raise ValueError('Prediction input reproduction required')
        # Validate exact timing and input/outcome prefix before aggregation.
        checked=evaluate_simulated_session(packet,bundle['metadata'],envelope,
            bundle['raw_opening'],bundle['completed_bars'])
        by_date[date]={symbol:(array,{}) for symbol,array in bundle['completed_bars'].items()}
        for prediction in packet['record']['predictions']:
            bars=sorted(bundle['raw_opening']['bars'][prediction['symbol']],key=lambda bar:bar['t'])
            rows.append(dict(date=date,symbol=prediction['symbol'],probability=prediction['probability'],
                signal_price=float(bars[-1]['c'])))
        receipts.append(dict(session_date=date,record_sha256=packet['record_sha256'],
            outcome_sip_sha256=bundle['outcome_sip_sha256'],anchor=checked['anchor']))
    missing=sorted(expected-set(by_date))
    outcomes=[]
    for cost,delay in VARIANTS:
        outcome=portfolio(rows,by_date,30,'target_60',.65,cost,delay)
        metrics=accounting_metrics(outcome,rows)
        outcome.update(metrics=metrics,cost_diagnostic=diagnostic(outcome))
        outcomes.append(outcome)
    primary=outcomes[0]
    risk_ok=all(all(result['metrics'][key] for key in
        ['category_budget_pass','stock_budget_pass','max_positions_pass','planned_risk_pass']) for result in outcomes)
    return dict(status='cumulative_simulation_from_supplied_inputs_only',
        expected_completed_sessions=len(expected),verified_input_sessions=len(by_date),
        missing_completed_sessions=missing,completed_calendar_coverage_pct=len(by_date)/len(expected)*100 if expected else None,
        coverage_complete=bool(expected) and not missing,receipts=sorted(receipts,key=lambda r:r['session_date']),
        outcomes=outcomes,probability_diagnostic=probability_diagnostic(rows,by_date),
        cumulative_risk_checks_pass=risk_ok,
        performance_screen_pass=bool(primary['target_screen_pass'] and risk_ok and expected and not missing),
        independent_validation_pass=False,production_approved=False,orders=False,
        limitations=['Pure evaluator cannot authenticate caller-provided bundles; CLI verifies remote digests and reproduction',
            'Missing dates prevent full-period validation; observed-span simulation is not a complete forward period',
            'Frozen OHLC virtual sleeve only; not whole production account or actual broker fills',
            'Frozen guard uses prior end-of-day peaks, not an intraday high-water mark',
            'At most one simultaneous entry per symbol per day: entry cutoff cannot be exercised by later entries',
            'All costs and adverse simultaneous low marks are assumptions',
            '100 active days and Wilson lower bound >=90% are a screen, not a guarantee or live-trading authorization'])


def audit_series(run_ids,backup,model_dir,output):
    if len(run_ids)!=len(set(run_ids)): raise ValueError('Duplicate run id')
    envelope=read_manifest(model_dir);bundles=[];inspections=[];excluded=[]
    calendar=completed_calendar(envelope,backup)
    for run_id in run_ids:
        inspection,accepted,rejected=load_verified_sessions(run_id,backup,model_dir)
        bundles.extend(accepted);inspections.append(inspection);excluded.extend(rejected)
    report=simulate_series(bundles,envelope,calendar['completed_sessions'])
    report.update(status='authenticated_inputs_cumulative_simulation_only',
        manifest_sha256=envelope['manifest_sha256'],calendar=calendar,
        input_run_ids=run_ids,inspections=inspections,excluded=excluded,
        authenticated_archive_digests=all(i['authenticated_archive_digests'] for i in inspections),
        provenance_verified_sessions=len(bundles))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(dict(output=str(output),sessions=len(bundles),
        missing_sessions=report['missing_completed_sessions'],
        active_days=report['outcomes'][0]['active_days'],net_usd=report['outcomes'][0]['profit_usd'],
        performance_screen_pass=report['performance_screen_pass'],independent_validation_pass=False,orders=False)))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',type=int,action='append',required=True)
    parser.add_argument('--backup',type=Path,default=Path('research_runs/prospective_backups'))
    parser.add_argument('--model-dir',type=Path,default=Path('research_prospective/control_v2'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/prospective_series/results.json'))
    args=parser.parse_args();load_dotenv();audit_series(args.run_id,args.backup,args.model_dir,args.output)
