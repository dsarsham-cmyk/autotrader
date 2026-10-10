"""Isolated, date-effective split normalization of historical opening inputs.

GET-only research audit. Current downloaded corporate-action records are NOT
authenticated point-in-time announcements. No model/portfolio/order changes.
"""
import argparse
from datetime import date as calendar_date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

from active_stock_research import SYMBOLS
from causal_opening_inventory import FEATURES, load_observations, opening_rows
from macro_context_research import context
from prospective_model_collector import get_json

URL = 'https://data.alpaca.markets/v1/corporate-actions'


def iso_date(value):
    if not isinstance(value, str) or calendar_date.fromisoformat(value).isoformat() != value:
        raise ValueError('Canonical calendar date required')
    return value


def events_from_pages(pages, symbols):
    """Fail on duplicates/conflicting unit changes rather than applying twice."""
    allowed = set(symbols)
    events = []
    seen_ids = set()
    seen_dates = set()
    for page in pages:
        actions = page.get('corporate_actions')
        if not isinstance(actions, dict) or set(actions) - {'forward_splits', 'reverse_splits'}:
            raise ValueError('Unexpected corporate action response')
        for kind, records in actions.items():
            if not isinstance(records, list):
                raise ValueError('Split record list required')
            for item in records:
                symbol = item['symbol']
                effective = iso_date(item['ex_date'])
                iso_date(item['process_date'])
                identity = item['id']
                if symbol not in allowed or not isinstance(identity, str) or not identity:
                    raise ValueError('Unexpected split symbol or identity')
                if identity in seen_ids or (symbol, effective) in seen_dates:
                    raise ValueError('Duplicate or ambiguous split event')
                old, new = item['old_rate'], item['new_rate']
                if any(isinstance(v, bool) or not isinstance(v, (int, float)) or
                       not math.isfinite(v) or v <= 0 for v in [old, new]):
                    raise ValueError('Finite positive split rates required')
                ratio = new / old
                if not math.isfinite(ratio) or (kind == 'forward_splits' and ratio <= 1) or (
                        kind == 'reverse_splits' and ratio >= 1):
                    raise ValueError('Split ratio/type mismatch')
                seen_ids.add(identity)
                seen_dates.add((symbol, effective))
                events.append(dict(symbol=symbol, ex_date=effective, ratio=ratio,
                                   id=identity, kind=kind, process_date=item['process_date']))
    return sorted(events, key=lambda item: (item['symbol'], item['ex_date']))


def collect_receipt(path):
    """Immutable own receipts, bounded complete pagination, no HTTP mutations."""
    if path.exists():
        raise ValueError('Existing corporate-action receipt will not be overwritten')
    params = dict(symbols=','.join(SYMBOLS), types='forward_split,reverse_split',
                  start='2024-01-01', end='2026-10-01', limit=1000, sort='asc')
    pages, tokens = [], set()
    query = dict(params)
    for _ in range(10):
        page = get_json(URL, query)
        pages.append(page)
        token = page.get('next_page_token')
        if token is None:
            break
        if not isinstance(token, str) or not token or token in tokens:
            raise ValueError('Invalid or repeated pagination token')
        tokens.add(token)
        query = dict(params, page_token=token)
    else:
        raise ValueError('Corporate-action pagination cap reached')
    events_from_pages(pages, SYMBOLS)
    receipt = dict(url=URL, query=params, pages=pages,
                   collected_at=datetime.now(timezone.utc).isoformat(),
                   historical_announcement_receipt_authenticated=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as target:
        json.dump(receipt, target, indent=2, allow_nan=False)
    return receipt


def normalized_opening_rows(observations, events):
    """Change accumulated past units only when the split becomes effective.

    Price history / ratio; opening-volume history * ratio. Current intraday
    bars, current signal prices and previous output rows are never adjusted.
    A missing effective session applies the event before the next observed one.
    """
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
                        float(late.volume.sum()/opening.volume.sum()), (959-prior[-1]['minute'])/5]
                    by_date.setdefault(date, {})[symbol] = dict(date=date, symbol=symbol,
                        features=values, signal_price=float(opening.close.iloc[-1]))
            reasons[(date, symbol)] = reason
            closing = regular.loc[regular.minute >= 955]
            if not closing.empty:
                last = closing.iloc[-1]
                prior.append(dict(close=float(last.close), minute=int(last.minute),
                                  volume=float(opening.volume.sum())))
    for stocks in by_date.values():
        changes = np.asarray([r['features'][0] for r in stocks.values()])
        for row in stocks.values():
            row['features'] += [float(changes.mean()), float(np.mean(changes > 0))]
    return by_date, reasons, applications


def inspect(observations, events):
    baseline, reasons = opening_rows(observations)
    control, control_reasons, _ = normalized_opening_rows(observations, [])
    if baseline != control or reasons != control_reasons:
        raise ValueError('No-event builder must exactly reproduce original inputs')
    normalized, normalized_reasons, applications = normalized_opening_rows(observations, events)
    if reasons != normalized_reasons or {d: sorted(s) for d,s in baseline.items()} != {
            d: sorted(s) for d,s in normalized.items()}:
        raise ValueError('Normalization changed candidate eligibility')
    changes, event_effects = [], []
    for date, stocks in sorted(baseline.items()):
        for symbol, row in sorted(stocks.items()):
            other = normalized[date][symbol]
            if row['signal_price'] != other['signal_price']:
                raise ValueError('Current raw signal price changed')
            changed = [name for name,a,b in zip(FEATURES,row['features'],other['features'])
                       if not math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12)]
            if changed:
                changes.append(dict(date=date, symbol=symbol, changed_features=changed))
    for event in events:
        date, symbol = event['ex_date'], event['symbol']
        before = baseline.get(date, {}).get(symbol)
        after = normalized.get(date, {}).get(symbol)
        event_effects.append(dict(event, opening_features_available=before is not None,
            raw_features=dict(zip(FEATURES, before['features'])) if before else None,
            normalized_features=dict(zip(FEATURES, after['features'])) if after else None))
    return dict(status='exposed_historical_split_input_audit',
        no_event_reference_exact=True, eligibility_unchanged=True, raw_signal_prices_unchanged=True,
        opening_rows=sum(len(s) for s in baseline.values()), changed_rows=len(changes),
        changed_dates=len({r['date'] for r in changes}), changes=changes,
        events=event_effects, applications=applications, feature_names=FEATURES,
        orders=False, production_approved=False, independent_validation_pass=False,
        performance_screen_pass=False, economic_evaluation_performed=False,
        limitations=['Current corporate-action records are retrospective, not original delivery evidence',
            'Only forward/reverse splits, not dividends, spin-offs, mergers or renamed symbols',
            'Fixed current universe and historical data revisions remain',
            'Candidate eligibility and intraday execution prices unchanged; no profit claim',
            'Frozen prospective model and production inputs are not modified'])


def run(data, output, download=False):
    receipt_path = output/'corporate_actions_receipt.json'
    if download:
        load_dotenv(Path(__file__).parent/'.env')
        collect_receipt(receipt_path)
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    if receipt['url'] != URL or receipt['query'] != dict(symbols=','.join(SYMBOLS),
            types='forward_split,reverse_split', start='2024-01-01', end='2026-10-01', limit=1000, sort='asc'):
        raise ValueError('Wrong corporate-action receipt context')
    pages = receipt['pages']
    if not pages or pages[-1].get('next_page_token') is not None:
        raise ValueError('Incomplete corporate-action receipt')
    events = events_from_pages(pages, SYMBOLS)
    observations, evidence = load_observations(data)
    report = inspect(observations, events)
    report['evidence'] = evidence
    report['corporate_action_receipt_sha256'] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    report['source_sha256'] = {name: hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
        for name in ['split_context_audit.py','causal_opening_inventory.py','macro_context_research.py']}
    output.mkdir(parents=True, exist_ok=True)
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({key:report[key] for key in ['status','opening_rows','changed_rows',
        'changed_dates','no_event_reference_exact','orders','economic_evaluation_performed']}))
    for event in report['events']:
        print(json.dumps(dict(symbol=event['symbol'], date=event['ex_date'], ratio=event['ratio'],
            raw_gap=event['raw_features']['gap'] if event['raw_features'] else None,
            normalized_gap=event['normalized_features']['gap'] if event['normalized_features'] else None)))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/split_context_audit'))
    parser.add_argument('--download',action='store_true')
    args = parser.parse_args()
    run(args.data,args.output,args.download)
