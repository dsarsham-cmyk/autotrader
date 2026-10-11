"""Calendar-defined regular closes on corrected causal inputs; NO ORDERS.

Retrospective calendar receipts do not authenticate original publication.
Frozen collectors/builders remain unchanged. Missing current future closes
never determine opening eligibility; known prior half-day closes are retained.
"""
import argparse
from datetime import datetime,time,timezone
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from dotenv import load_dotenv
from active_stock_research import SYMBOLS
from causal_opening_inventory import load_observations
from causal_opening_inventory import FEATURES
from macro_context_research import context
from prospective_model_collector import get_json
from split_context_audit import iso_date,events_from_pages,normalized_opening_rows

URL='https://paper-api.alpaca.markets/v2/calendar'


def calendar_lookup(rows):
    if not isinstance(rows,list): raise ValueError('Calendar list required')
    result={}
    for row in rows:
        date=iso_date(row['date'])
        if date in result or row['open']!='09:30': raise ValueError('Duplicate or unsupported calendar open')
        close=time.fromisoformat(row['close'])
        if close.tzinfo or close.second or close.microsecond: raise ValueError('Exact local minute calendar close required')
        minute=close.hour*60+close.minute
        if not 678<=minute<=960: raise ValueError('Calendar close cannot support fixed execution horizon')
        result[date]=dict(close_minute=minute)
    return result


def clip_sessions(observations,calendar):
    if any(d not in calendar for days in observations.values() for d in days):
        raise ValueError('Observed date absent from exchange calendar')
    return {s:{d:r.loc[(r.minute>=570)&(r.minute<calendar[d]['close_minute'])].copy()
               for d,r in days.items()} for s,days in observations.items()}


def calendar_opening_rows(observations, events, calendar):
    """Change accumulated past units only when the split becomes effective.

    Price history / ratio; opening-volume history * ratio. Current intraday
    bars, current signal prices and previous output rows are never adjusted.
    A missing effective session applies the event before the next observed one.
    """
    observations = clip_sessions(observations, calendar)
    by_date, reasons, applications = {}, {}, []
    if any(e['symbol'] not in observations for e in events):
        raise ValueError('Split event has no observed symbol')
    for symbol, days in sorted(observations.items()):
        pending = sorted([e for e in events if e['symbol'] == symbol], key=lambda e: e['ex_date'])
        if len({e['ex_date'] for e in pending}) != len(pending):
            raise ValueError('Ambiguous split date')
        prior = []
        index = 0
        for date, regular in sorted(days.items()):
            expected_terminal = calendar[date]['close_minute'] - 1
            while index < len(pending) and pending[index]['ex_date'] <= date:
                event = pending[index]
                ratio = event['ratio']
                if not math.isfinite(ratio) or ratio <= 0:
                    raise ValueError('Invalid split ratio')
                for historical in prior:
                    historical['close'] /= ratio
                    historical['volume'] *= ratio
                applications.append(dict(symbol=symbol, effective_date=event['ex_date'],
                    applied_before_session=date, prior_records_rescaled=len(prior), ratio=ratio))
                index += 1
            opening = regular.loc[regular.minute < 600]
            reason = 'incomplete_opening'
            if opening.minute.tolist() == list(range(570, 600)):
                values, reason = context(opening, prior)
                if values is not None:
                    late = opening.loc[opening.minute >= 595]
                    values += [prior[-1]['close']/prior[-2]['close']-1,
                        float(late.close.iloc[-1]/late.open.iloc[0]-1),
                        float(late.volume.sum()/opening.volume.sum()), (prior[-1]['expected_terminal_minute']-prior[-1]['minute'])/5]
                    by_date.setdefault(date, {})[symbol] = dict(date=date, symbol=symbol,
                        features=values, signal_price=float(opening.close.iloc[-1]))
            reasons[(date, symbol)] = reason
            closing = regular.loc[regular.minute >= expected_terminal - 4]
            if not closing.empty:
                last = closing.iloc[-1]
                prior.append(dict(close=float(last.close), minute=int(last.minute), expected_terminal_minute=expected_terminal,
                                  volume=float(opening.volume.sum())))
    for stocks in by_date.values():
        changes = np.asarray([r['features'][0] for r in stocks.values()])
        for row in stocks.values():
            row['features'] += [float(changes.mean()), float(np.mean(changes > 0))]
    return by_date, reasons, applications


def inspect(observations, events, calendar):
    baseline, reasons, applications = normalized_opening_rows(observations, events)
    normal = {d: dict(close_minute=960) for d in calendar}
    control, control_reasons, control_applications = calendar_opening_rows(observations, events, normal)
    if (baseline, reasons, applications) != (control, control_reasons, control_applications):
        raise ValueError('16:00 control does not reproduce original builder')
    corrected, corrected_reasons, corrected_applications = calendar_opening_rows(observations, events, calendar)
    old = {(d,s):r for d,stocks in baseline.items() for s,r in stocks.items()}
    new = {(d,s):r for d,stocks in corrected.items() for s,r in stocks.items()}
    common = sorted(old.keys() & new.keys())
    changes = []
    for key in common:
        if old[key]['signal_price'] != new[key]['signal_price']:
            raise ValueError('Opening signal price changed')
        names = [name for name,a,b in zip(FEATURES,old[key]['features'],new[key]['features'])
                 if not math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12)]
        if names:
            changes.append(dict(date=key[0],symbol=key[1],features=names))
    removed = [dict(date=d,symbol=s,bars=int((frame.minute >= calendar[d]['close_minute']).sum()))
               for s,days in sorted(observations.items()) for d,frame in sorted(days.items())
               if (frame.minute >= calendar[d]['close_minute']).any()]
    return dict(status='exposed_historical_calendar_input_audit', normal_close_control_exact=True,
        baseline_rows=len(old),corrected_rows=len(new),common_rows=len(common),
        added_candidates=[dict(date=d,symbol=s) for d,s in sorted(new.keys()-old.keys())],
        removed_candidates=[dict(date=d,symbol=s) for d,s in sorted(old.keys()-new.keys())],
        changed_rows=len(changes),changed_dates=len({r['date'] for r in changes}),changes=changes,
        excluded_after_close_bars=sum(r['bars'] for r in removed),affected_symbol_sessions=removed,
        half_days=[d for d in sorted(calendar) if calendar[d]['close_minute']<960],
        common_raw_signal_prices_unchanged=True,split_applications=corrected_applications,
        orders=False,production_approved=False,independent_validation_pass=False,
        performance_screen_pass=False,economic_evaluation_performed=False,
        limitations=['Retrospective calendar and split records, not original delivery evidence',
                    'Frozen models, collectors and production inputs remain unchanged',
                    'Input correction requires separate retraining and economic evaluation',
                    'After-hours prices are not invalid; their regular-session classification was wrong'])


def run(data, output, split_receipt, download=False):
    output.mkdir(parents=True,exist_ok=True)
    receipt_path=output/'calendar_receipt.json'
    query=dict(start='2024-01-01',end='2026-10-01')
    if download:
        if receipt_path.exists(): raise ValueError('Calendar receipt already exists')
        load_dotenv(Path(__file__).parent/'.env')
        rows=get_json(URL,query)
        calendar_lookup(rows)
        receipt=dict(url=URL,query=query,received_utc=datetime.now(timezone.utc).isoformat(),rows=rows)
        with receipt_path.open('x',encoding='utf-8') as handle:
            json.dump(receipt,handle,indent=2,allow_nan=False)
    receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
    if receipt['url']!=URL or receipt['query']!=query: raise ValueError('Wrong calendar context')
    calendar=calendar_lookup(receipt['rows'])
    split=json.loads(split_receipt.read_text(encoding='utf-8'))
    expected=dict(symbols=','.join(SYMBOLS),types='forward_split,reverse_split',
                  start='2024-01-01',end='2026-10-01',limit=1000,sort='asc')
    if split['url']!='https://data.alpaca.markets/v1/corporate-actions' or split['query']!=expected or not split['pages'] or split['pages'][-1].get('next_page_token') is not None:
        raise ValueError('Wrong or incomplete split receipt')
    observations,evidence=load_observations(data)
    report=inspect(observations,events_from_pages(split['pages'],SYMBOLS),calendar)
    report.update(evidence=evidence,calendar_receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        split_receipt_sha256=hashlib.sha256(split_receipt.read_bytes()).hexdigest(),
        source_sha256={name:hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for name in ['calendar_regular_context.py','split_context_audit.py','macro_context_research.py',
                         'causal_opening_inventory.py']})
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['status','baseline_rows','corrected_rows','changed_rows',
        'changed_dates','excluded_after_close_bars','half_days','normal_close_control_exact','orders']}))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/calendar_regular_context'))
    parser.add_argument('--split-receipt',type=Path,default=Path('research_runs/split_context_audit/corporate_actions_receipt.json'))
    parser.add_argument('--download',action='store_true')
    args=parser.parse_args()
    run(args.data,args.output,args.split_receipt,args.download)
