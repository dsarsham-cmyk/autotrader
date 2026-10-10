"""GET exchange calendar to audit observed research ledger coverage, NO ORDERS."""
import argparse
from datetime import datetime,timezone,time
import hashlib
import json
from pathlib import Path
from dotenv import load_dotenv
from prospective_model_collector import get_json
from prospective_outcome_audit import save_once_or_identical


def calendar_dates(rows,first,last):
    dates={}
    for row in rows:
        date=row['date']
        if date in dates or not first<=date<=last: raise ValueError('Duplicate/out-of-range calendar date')
        opening=time.fromisoformat(row['open']);closing=time.fromisoformat(row['close'])
        if closing<=opening: raise ValueError('Invalid calendar session')
        dates[date]=row
    return dates


def inspect(source,calendar):
    cases=[]
    for case in source['cases']:
        first=min(f['test_first'] for f in case['folds']);last=max(f['test_last'] for f in case['folds'])
        expected={d:row for d,row in calendar.items() if first<=d<=last}
        for outcome in case['outcomes']:
            dates=[d['date'] for d in outcome['daily']]
            if len(dates)!=len(set(dates)): raise ValueError('Duplicate ledger date')
            missing=sorted(set(expected)-set(dates));extra=sorted(set(dates)-set(expected))
            unsupported=[];early=[]
            horizon=outcome.get('horizon_minutes',60)
            if horizon not in (60,120) or isinstance(horizon,bool): raise ValueError('Unsupported research horizon')
            latest_exit=570+30+outcome['delay']+horizon
            for date,row in expected.items():
                close=time.fromisoformat(row['close']);close_minute=close.hour*60+close.minute
                if row['open']!='09:30' or latest_exit>=close_minute: unsupported.append(date)
                if row['close']!='16:00': early.append(date)
            calendar_complete=bool(expected) and not missing and not extra and not unsupported
            cases.append(dict(model=case['model'],feature_set=case.get('feature_set'),
                threshold=outcome['threshold'],costs_bps=outcome['costs_bps'],delay=outcome['delay'],horizon_minutes=horizon,
                first=first,last=last,expected_exchange_sessions=len(expected),ledger_sessions=len(dates),
                missing_ledger_dates=missing,non_calendar_ledger_dates=extra,
                unsupported_session_windows=unsupported,early_close_dates=early,
                calendar_coverage_complete=calendar_complete,
                full_period_profit_interpretable=bool(calendar_complete and outcome['full_period_coverage_complete']),
                independent_validation_pass=False))
    return dict(status='retrospective_exchange_calendar_coverage_audit',cases=cases,
        all_observed_spans_cover_calendar=bool(cases) and all(c['calendar_coverage_complete'] for c in cases),
        independent_validation_pass=False,production_approved=False,orders=False,
        limitations=['Retrospective provider calendar receipt is not a point-in-time original schedule receipt',
            'Missing ledger dates may be unknown selected outcomes, not absence of forecasts or losing days',
            'Complete calendar coverage does not authenticate stock prices/fills, original delivery or profitability',
            'Only declared60/120-minute research horizons; not full production engine session/EOD behavior'])


def run(inputs,output):
    load_dotenv();sources=[json.loads(p.read_bytes()) for p in inputs]
    if any(not s['status'].startswith('completed_') for s in sources): raise ValueError('Completed source studies required')
    first=min(f['test_first'] for s in sources for c in s['cases'] for f in c['folds'])
    last=max(f['test_last'] for s in sources for c in s['cases'] for f in c['folds'])
    rows=get_json('https://paper-api.alpaca.markets/v2/calendar',{'start':first,'end':last})
    if not isinstance(rows,list): raise ValueError('Invalid calendar response')
    calendar=calendar_dates(rows,first,last)
    output.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(dict(retrieved_utc=datetime.now(timezone.utc).isoformat(),start=first,end=last,calendar=rows),
        sort_keys=True,separators=(',',':')).encode();receipt=hashlib.sha256(raw).hexdigest()
    save_once_or_identical(output/'receipts'/f'{receipt}.json',raw)
    report=dict(status='completed_retrospective_calendar_audit',calendar_sha256=receipt,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),
        sources=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),audit=inspect(s,calendar))
            for p,s in zip(inputs,sources)],orders=False,independent_validation_pass=False,production_approved=False)
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(dict(calendar_sessions=len(calendar),sources=len(sources),
        all_calendar_coverage=all(s['audit']['all_observed_spans_cover_calendar'] for s in report['sources']),
        orders=False)));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,action='append',required=True)
    p.add_argument('--output',type=Path,default=Path('research_runs/calendar_audit'))
    a=p.parse_args();run(a.input,a.output)
