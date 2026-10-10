"""GET-only boundary liquidity context; modeled fills are not actual executions."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from paper_fill_quote_audit import quote_match
from prospective_model_collector import get_json
from prospective_outcome_audit import save_once_or_identical
from quote_cost_audit import fetch_pages


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def select_trades(trades, maximum=40):
    if maximum < 1: raise ValueError('Positive sample bound required')
    ordered=sorted(trades,key=lambda t:(t['date'],t['symbol']))
    keys=[(t['date'],t['symbol']) for t in ordered]
    if len(set(keys))!=len(keys): raise ValueError('Duplicate trade identity')
    indices=np.linspace(0,len(ordered)-1,min(maximum,len(ordered))).astype(int) if ordered else []
    return [ordered[int(i)] for i in indices]


def boundary(trade, phase):
    if phase not in ('entry','exit'): raise ValueError('Unknown phase')
    entry=trade['entry_minute'];exit_minute=trade['exit_minute']
    if type(entry) is not int or type(exit_minute) is not int or entry!=46 or not entry<=exit_minute<=106:
        raise ValueError('Unsupported execution window')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',trade['date']): raise ValueError('Invalid date')
    return (pd.Timestamp(trade['date']+' 09:30',tz='America/New_York')+
            pd.Timedelta(minutes=trade[phase+'_minute'])).tz_convert('UTC')


def context_match(point, quotes):
    matched=quote_match(dict(transaction_time=point.isoformat(),price=1,qty=1,side='buy'),quotes)
    allowed={'status','quote_timestamp','quote_age_seconds','bid','ask','displayed_bid_size_raw',
             'displayed_ask_size_raw','full_quoted_spread_bps'}
    result={k:v for k,v in matched.items() if k in allowed}
    if result['status']=='matched_paper_fill_quote': result['status']='observed_fresh_model_boundary_quote'
    if result['status']=='no_quote_at_or_before_fill': result['status']='no_quote_at_or_before_boundary'
    return dict(result,context_only=True,actual_execution_time_authenticated=False,total_real_cost_measured=False)


def run(reference, output):
    load_dotenv();output.mkdir(parents=True,exist_ok=True)
    original=json.loads(reference.read_bytes())
    if original['status']!='completed_exposed_split_predictive_comparison': raise ValueError('Completed reference required')
    cases=[c for c in original['cases'] if c['feature_set']=='date_effective_split_context' and c['model']=='logistic']
    if len(cases)!=1: raise ValueError('Unique reference case required')
    outcomes=[o for o in cases[0]['outcomes'] if o['threshold']==.65 and o['costs_bps']==10 and o['delay']==16]
    if len(outcomes)!=1 or not outcomes[0]['full_period_coverage_complete']: raise ValueError('Complete unique outcome required')
    for name,expected in original['dependency_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected:
            raise ValueError('Reference source changed')
    cohort=outcomes[0]['trades'];sample=select_trades(cohort)
    report=dict(status='running_modeled_boundary_quote_audit',reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        cohort_sha256=digest(cohort),cohort_trades=len(cohort),sampled_trade_ids=[(t['date'],t['symbol']) for t in sample],
        protocol=dict(sample_maximum=40,selection='equally spaced chronological date/symbol indices, no P&L selection',
            model='logistic',feature_set='date_effective_split_context',probability_gate=.65,cost_bps=10,delay=16,
            feed='sip',quote_seed_seconds=2,query_after_boundary_seconds=1,maximum_quote_age_seconds=2),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),
        dependency_sha256={n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in
            ['paper_fill_quote_audit.py','quote_cost_audit.py','prospective_model_collector.py','prospective_outcome_audit.py']},
        observations=[],orders=False,cost_assumptions_changed=False,production_approved=False,independent_validation_pass=False,
        limitations=['Exposed selected-model trade cohort, not representative or independent execution evidence',
            'Exit minute boundary is not authenticated intraminute stop/target execution time',
            'Entry boundary can precede first bar trade; no modeled fill versus quote comparison',
            'No fees, latency, impact, queue, fillability or raw quote-size share units are inferred',
            'Historical quote delivery and revisions are unauthenticated; unchanged10/20bps cost assumptions'])
    for trade in sample:
        symbol=trade['symbol']
        if not re.fullmatch(r'[A-Z][A-Z0-9.]{0,9}',symbol): raise ValueError('Invalid symbol')
        for phase in ('entry','exit'):
            point=boundary(trade,phase)
            query=dict(symbol=symbol,start=(point-pd.Timedelta(seconds=2)).isoformat(),
                end=(point+pd.Timedelta(seconds=1)).isoformat(),feed='sip',maximum_pages=10)
            query_id=digest(query);target=output/'quotes'/f'{query_id}.json'
            observation=dict(date=trade['date'],symbol=symbol,phase=phase,boundary_utc=point.isoformat(),query_id=query_id)
            try:
                if target.exists(): packet=json.loads(target.read_bytes())
                else:
                    payload=fetch_pages(lambda p:get_json('https://data.alpaca.markets/v2/stocks/quotes',p),
                        symbol,query['start'],query['end'],maximum=10)
                    packet=dict(query=query,retrieved_utc=datetime.now(timezone.utc).isoformat(),payload=payload)
                    save_once_or_identical(target,json.dumps(packet,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
                if packet['query']!=query or not packet['payload']['pagination_complete']: raise ValueError('Receipt identity changed')
                observation.update(context_match(point,packet['payload']['quotes']),
                    receipt_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
            except (RuntimeError,ValueError) as error:
                observation.update(status='quote_evidence_unavailable',error_type=type(error).__name__,context_only=True,
                    actual_execution_time_authenticated=False,total_real_cost_measured=False)
            report['observations'].append(observation)
            print(json.dumps(dict(observation=len(report['observations']),symbol=symbol,phase=phase,status=observation['status'])),flush=True)
            (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    unique={o['query_id']:o for o in report['observations']}
    known=[o['full_quoted_spread_bps'] for o in unique.values() if o['status']=='observed_fresh_model_boundary_quote']
    report.update(status='completed_modeled_boundary_quote_audit',unique_queries=len(unique),
        phase_status_counts=dict(Counter(o['status'] for o in report['observations'])),
        unique_query_status_counts=dict(Counter(o['status'] for o in unique.values())),
        unique_query_median_full_spread_bps=float(np.median(known)) if known else None,
        unique_query_p95_full_spread_bps=float(np.percentile(known,95)) if known else None)
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,default=Path('research_runs/split_predictive/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/modeled_boundary_quotes'))
    args=p.parse_args();run(args.reference,args.output)
