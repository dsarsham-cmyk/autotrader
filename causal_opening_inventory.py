"""Opening signals must not depend on later full-session data completeness.

Research input builder, not an execution engine or independently valid dataset.
Missing later outcomes stay unknown, never simulated wins or no-trade days.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from active_stock_research import SYMBOLS,hash_file,load_universe
from macro_context_research import proxy_sessions,context,FIELDS

FEATURES=FIELDS+['prior_return','last_five_return','last_five_volume_share',
    'prior_terminal_age_fraction','cross_section_mean_return','positive_breadth']


def load_observations(directory):
    observations={};evidence={}
    for symbol in SYMBOLS:
        path=directory/f'{symbol}.csv';meta=json.loads(path.with_suffix('.metadata.json').read_text())
        actual=hash_file(path)
        if meta.get('feed')!='sip' or meta.get('adjustment')!='raw' or meta.get('sha256')!=actual:
            raise ValueError('Verified own SIP/raw input required')
        observations[symbol]=proxy_sessions(pd.read_csv(path),symbol)
        evidence[symbol]=dict(sha256=actual,regular_dates=len(observations[symbol]))
    return observations,evidence


def opening_rows(observations):
    """Extract current features before appending today's closing history."""
    by_date={};reasons={}
    for symbol,days in sorted(observations.items()):
        prior=[]
        for date,regular in sorted(days.items()):
            opening=regular.loc[regular.minute<600]
            values=None;reason='incomplete_opening'
            if opening.minute.tolist()==list(range(570,600)):
                values,reason=context(opening,prior)
                if values is not None:
                    late=opening.loc[opening.minute>=595]
                    values=values+[prior[-1]['close']/prior[-2]['close']-1,
                        float(late.close.iloc[-1]/late.open.iloc[0]-1),
                        float(late.volume.sum()/opening.volume.sum()),(959-prior[-1]['minute'])/5]
                    by_date.setdefault(date,{})[symbol]=dict(date=date,symbol=symbol,
                        features=values,signal_price=float(opening.close.iloc[-1]))
            reasons[(date,symbol)]=reason
            closing=regular.loc[regular.minute>=955]
            if not closing.empty:
                last=closing.iloc[-1]
                prior.append(dict(close=float(last.close),minute=int(last.minute),
                    volume=float(opening.volume.sum())))
    for date,stocks in by_date.items():
        changes=np.asarray([r['features'][0] for r in stocks.values()])
        for row in stocks.values():
            row['features']+=[float(changes.mean()),float(np.mean(changes>0))]
    return by_date,reasons


def inspect(observations,complete):
    signals,reasons=opening_rows(observations);missing=[];changed=[];inventory=[]
    for date,stocks in sorted(signals.items()):
        kept={s:r for s,r in stocks.items() if s in complete.get(date,{})}
        old_mean=float(np.mean([r['features'][0] for r in kept.values()])) if kept else None
        old_breadth=float(np.mean([r['features'][0]>0 for r in kept.values()])) if kept else None
        causal_mean=next(iter(stocks.values()))['features'][-2]
        causal_breadth=next(iter(stocks.values()))['features'][-1]
        for symbol,row in stocks.items():
            if symbol not in kept:
                regular=observations[symbol][date]
                # Fixed entry46/47 with60-minute horizon finishes106/107.
                # This coverage check is retrospective OUTCOME metadata only;
                # it NEVER determines today's opening candidate membership.
                minute_set=set(int(v)-570 for v in regular.minute)
                missing.append(dict(date=date,symbol=symbol,regular_bars=len(regular),
                    opening_available=True,full_outcome_available=False,
                    fixed_entry_horizon_coverage_complete=set(range(46,108))<=minute_set,
                    status='unknown_outcome_not_no_trade_or_win'))
        if old_mean is None or old_mean!=causal_mean or old_breadth!=causal_breadth:
            changed.append(dict(date=date,causal_candidates=len(stocks),complete_only_candidates=len(kept),
                causal_mean_return=causal_mean,complete_only_mean_return=old_mean,
                causal_positive_breadth=causal_breadth,complete_only_positive_breadth=old_breadth))
        inventory.append(dict(date=date,opening_candidates=len(stocks),
            complete_outcome_candidates=len(kept),missing_outcome_candidates=len(stocks)-len(kept)))
    reason_counts={}
    for reason in reasons.values(): reason_counts[reason]=reason_counts.get(reason,0)+1
    return dict(status='exposed_historical_causal_opening_inventory',feature_names=FEATURES,
        opening_candidate_rows=sum(len(s) for s in signals.values()),opening_dates=len(signals),
        full_outcome_missing_rows=len(missing),missing_outcomes=missing,
        excluded_rows_with_complete_fixed_trade_window=sum(x['fixed_entry_horizon_coverage_complete'] for x in missing),
        cross_section_changed_dates=len(changed),cross_section_changes=changed,
        eligibility_reason_counts=reason_counts,inventory=inventory,
        orders=False,production_approved=False,independent_validation_pass=False,
        performance_screen_pass=False,
        limitations=['Feature builder is a replacement16-feature context, not exact21-feature causal ablation',
            'No probabilistic forecasts, trades or profit evaluation performed by this inventory',
            'Complete fixed-window coverage alone does not authenticate fills or implement a sparse-outcome simulator',
            'Past terminal close must be15:55-or-later; current future close never qualifies current opening',
            'Opening dates are observed-provider dates, not an independently complete exchange calendar',
            'Missing whole sessions remain invisible without calendar and independent receipt evidence',
            'Current fixed universe, historical revisions/raw corporate actions and delivery timing remain biased'])


def run(directory,output):
    observations,evidence=load_observations(directory);complete,old=load_universe(directory)
    if any(evidence[s]['sha256']!=old['hashes'][s] for s in SYMBOLS):
        raise ValueError('Input changed between inventory and original loader')
    report=inspect(observations,complete);report['evidence']=evidence
    report['dependency_sha256']={name:hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
        for name in ['causal_opening_inventory.py','macro_context_research.py','active_stock_research.py','intraday_research.py']}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({k:report[k] for k in ['status','opening_candidate_rows','opening_dates',
        'full_outcome_missing_rows','cross_section_changed_dates','orders']}));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--output',type=Path,default=Path('research_runs/causal_opening_inventory/results.json'))
    a=p.parse_args();run(a.data,a.output)
