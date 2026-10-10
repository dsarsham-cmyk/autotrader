"""GET-only paper execution diagnostic; never reduce assumed real costs."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import re
import pandas as pd
from dotenv import load_dotenv
from prospective_model_collector import get_json
from prospective_outcome_audit import save_once_or_identical
from quote_cost_audit import fetch_pages

PROTOCOL=dict(maximum_recent_fill_activities=20,feed='sip',quote_seed_seconds=2,
    query_after_fill_seconds=1,maximum_matching_quote_age_seconds=2,
    matched_quote='latest timestamp at or before activity transaction_time',orders=False)


def quote_match(activity,quotes):
    fill=pd.Timestamp(activity['transaction_time'])
    if fill.tzinfo is None: raise ValueError('Aware fill timestamp required')
    price=float(activity['price']);qty=float(activity['qty']);side=activity['side']
    if side not in ('buy','sell') or not math.isfinite(price) or not math.isfinite(qty) or min(price,qty)<=0:
        raise ValueError('Invalid fill activity')
    points={}
    for quote in quotes:
        stamp=pd.Timestamp(quote['t'])
        if stamp.tzinfo is None: raise ValueError('Aware quote timestamp required')
        if stamp>fill: continue
        state=tuple(float(quote.get(k,0)) for k in ['bp','ap','bs','as'])
        if stamp in points and points[stamp]!=state: points[stamp]=None
        else: points[stamp]=state
    if not points: return dict(status='no_quote_at_or_before_fill')
    stamp=max(points);state=points[stamp];age=(fill-stamp).total_seconds()
    if state is None: return dict(status='ambiguous_terminal_quote',quote_age_seconds=age)
    bid,ask,bs,az=state
    if not all(math.isfinite(v) for v in state) or bid<=0 or ask<bid or min(bs,az)<=0:
        return dict(status='invalid_terminal_quote',quote_age_seconds=age)
    if age>2: return dict(status='stale_terminal_quote',quote_age_seconds=age)
    mid=(bid+ask)/2;adverse=price-mid if side=='buy' else mid-price
    return dict(status='matched_paper_fill_quote',quote_timestamp=stamp.isoformat(),quote_age_seconds=age,
        bid=bid,ask=ask,displayed_bid_size_raw=bs,displayed_ask_size_raw=az,
        full_quoted_spread_bps=(ask-bid)/mid*10000,
        signed_fill_vs_contemporaneous_mid_bps=adverse/mid*10000,
        fill_inside_or_at_displayed_spread=bid<=price<=ask,
        decision_to_execution_slippage_measured=False,total_real_cost_measured=False)


def select_activities(rows):
    if not isinstance(rows,list) or len(rows)>20: raise ValueError('Bounded activity list required')
    ids=[];timestamps=[]
    for row in rows:
        if row.get('activity_type')!='FILL': raise ValueError('Unexpected activity type')
        ids.append(row['id']);stamp=pd.Timestamp(row['transaction_time'])
        if stamp.tzinfo is None: raise ValueError('Aware activity timestamp required')
        timestamps.append(stamp)
    if len(ids)!=len(set(ids)): raise ValueError('Duplicate activity id')
    if timestamps!=sorted(timestamps,reverse=True): raise ValueError('Descending activity ordering required')
    return rows


def run(output):
    load_dotenv();output.mkdir(parents=True,exist_ok=True)
    activities=select_activities(get_json('https://paper-api.alpaca.markets/v2/account/activities',
        dict(activity_types='FILL',direction='desc',page_size=20)))
    raw=json.dumps(dict(retrieved_utc=datetime.now(timezone.utc).isoformat(),activities=activities),
        sort_keys=True,separators=(',',':')).encode();receipt=hashlib.sha256(raw).hexdigest()
    save_once_or_identical(output/'activity_receipts'/f'{receipt}.json',raw)
    report=dict(status='running_recent_paper_fill_quote_audit',protocol=PROTOCOL,activity_receipt_sha256=receipt,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),
        dependency_sha256={n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in
            ['prospective_model_collector.py','prospective_outcome_audit.py','quote_cost_audit.py']},
        fills=[],orders=False,cost_assumptions_changed=False,independent_validation_pass=False,production_approved=False,
        limitations=['Paper activities are simulated execution, not real-money fill/cost evidence',
            'Latest20 activities are bounded and recent, not representative market execution',
            'Contemporaneous quote comparison omits decision latency, market impact, queues and fees',
            'Historical NBBO delivery/revisions and actual matching size remain unauthenticated',
            'No risk/strategy/cost change or model promotion follows automatically'])
    for index,activity in enumerate(activities):
        symbol=activity['symbol'];identity=hashlib.sha256(json.dumps(activity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        result=dict(activity_sha256=identity,symbol=symbol,side=activity['side'],
            fill_timestamp=activity['transaction_time'],price=activity['price'],quantity=activity['qty'])
        if not re.fullmatch(r'[A-Z][A-Z0-9.]{0,9}',symbol): result['status']='unsupported_non_equity_symbol'
        else:
            fill=pd.Timestamp(activity['transaction_time']);start=(fill-pd.Timedelta(seconds=2)).isoformat();end=(fill+pd.Timedelta(seconds=1)).isoformat()
            query=dict(symbol=symbol,start=start,end=end,feed='sip')
            target=output/'quotes'/f'{identity}.json'
            try:
                if target.exists():
                    packet=json.loads(target.read_bytes())
                    if packet['query']!=query or not packet['payload']['pagination_complete']: raise ValueError('Quote receipt identity changed')
                else:
                    payload=fetch_pages(lambda params:get_json('https://data.alpaca.markets/v2/stocks/quotes',params),symbol,start,end,maximum=10)
                    packet=dict(query=query,retrieved_utc=datetime.now(timezone.utc).isoformat(),payload=payload)
                    encoded=json.dumps(packet,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
                    save_once_or_identical(target,encoded)
                result.update(quote_match(activity,packet['payload']['quotes']),
                    quote_receipt_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),pagination_complete=True)
            except (RuntimeError,ValueError) as error:
                result.update(status='quote_evidence_unavailable',error_type=type(error).__name__)
        report['fills'].append(result)
        print(json.dumps(dict(fill=index+1,symbol=symbol,status=result['status'],orders=False)),flush=True)
        (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    matched=[f for f in report['fills'] if f['status']=='matched_paper_fill_quote']
    report.update(status='completed_recent_paper_fill_quote_audit',matched_activities=len(matched),
        missing_or_unmatched_activities=len(activities)-len(matched),
        observed_first_activity=activities[-1]['transaction_time'] if activities else None,
        observed_last_activity=activities[0]['transaction_time'] if activities else None)
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('research_runs/paper_fill_quote_audit'))
    run(p.parse_args().output)
