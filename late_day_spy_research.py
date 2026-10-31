"""Fixed, exposed historical SPY late-day experiment. No order or deployment API."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import pandas as pd
from calendar_regular_context import calendar_lookup
from predictive_research import wilson
from split_context_audit import events_from_pages

PROTOCOL_PATH = Path('research_prospective/late_day_spy_long_v1/protocol.json')
PROTOCOL_SHA = 'a036d619d61f875f11f12cccf53f49c5bf12f418b6b9c4883a2db1aa161dd064'
SPLIT_URL = 'https://data.alpaca.markets/v1/corporate-actions'
QUERY = dict(symbols='SPY', types='forward_split,reverse_split', start='2024-01-01',
             end='2026-10-01', limit=1000, sort='asc')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_protocol():
    if sha(PROTOCOL_PATH) != PROTOCOL_SHA:
        raise ValueError('Frozen exploratory protocol changed')
    return json.loads(PROTOCOL_PATH.read_text(encoding='utf-8'))


def collect_splits(path):
    """Explicit GET-only metadata permission; never price download or broker writes."""
    if path.exists():
        raise ValueError('Existing receipt cannot be overwritten')
    from dotenv import load_dotenv
    from prospective_model_collector import get_json
    load_dotenv(Path(__file__).parent / '.env')
    pages = []
    token = None
    seen = set()
    for _ in range(10):
        query = dict(QUERY)
        if token:
            query['page_token'] = token
        page = get_json(SPLIT_URL, query)
        pages.append(page)
        token = page.get('next_page_token')
        if not token:
            break
        if token in seen:
            raise ValueError('Repeated corporate action token')
        seen.add(token)
    else:
        raise ValueError('Incomplete corporate action pagination')
    events_from_pages(pages, ['SPY'])
    receipt = dict(url=SPLIT_URL, query=QUERY, pages=pages,
                   received_utc=datetime.now(timezone.utc).isoformat(),
                   retrospective_not_original_delivery=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2, allow_nan=False)


def load_inputs(data, calendar_path, split_path):
    protocol = load_protocol()
    metadata_path = data.with_suffix('.metadata.json')
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    actual = sha(data)
    if (actual != protocol['data_sha256'] or metadata.get('sha256') != actual or
            metadata.get('feed') != 'sip' or metadata.get('adjustment') != 'raw' or
            metadata.get('symbol') != 'SPY'):
        raise ValueError('Verified frozen SPY SIP/raw input required')
    receipt = json.loads(calendar_path.read_text(encoding='utf-8'))
    if (receipt.get('url') != 'https://paper-api.alpaca.markets/v2/calendar' or
            receipt.get('query') != dict(start='2024-01-01', end='2026-10-01')):
        raise ValueError('Wrong calendar scope')
    calendar = calendar_lookup(receipt['rows'])
    splits = json.loads(split_path.read_text(encoding='utf-8'))
    if (splits.get('url') != SPLIT_URL or splits.get('query') != QUERY or
            not splits.get('pages') or splits['pages'][-1].get('next_page_token')):
        raise ValueError('Complete SPY-specific split receipt required')
    events = events_from_pages(splits['pages'], ['SPY'])
    frame = pd.read_csv(data)
    if set(frame.symbol.unique()) != {'SPY'}:
        raise ValueError('Unexpected symbol')
    timestamps = pd.to_datetime(frame.timestamp, utc=True)
    if timestamps.duplicated().any() or (timestamps.dt.second != 0).any():
        raise ValueError('Duplicate/nonminute timestamps')
    local = timestamps.dt.tz_convert('America/New_York')
    frame['date'] = local.dt.strftime('%Y-%m-%d')
    frame['minute'] = local.dt.hour * 60 + local.dt.minute
    sessions = {}
    for date, group in frame.groupby('date'):
        if date not in calendar:
            continue  # Provider extended-hours/closed dates never define sessions.
        regular = group.loc[(group.minute >= 570) & (group.minute < calendar[date]['close_minute'])]
        rows = {}
        for row in regular.itertuples():
            values = [float(getattr(row, name)) for name in ['open', 'high', 'low', 'close', 'volume']]
            if (not all(math.isfinite(v) for v in values) or min(values[:4]) <= 0 or
                    values[4] < 0 or values[1] < max(values[:4]) or values[2] > min(values[:4])):
                raise ValueError('Invalid regular OHLCV')
            rows[int(row.minute)] = values
        sessions[date] = rows
    return sessions, calendar, events, dict(data_sha256=actual, metadata_sha256=sha(metadata_path),
        calendar_receipt_sha256=sha(calendar_path), split_receipt_sha256=sha(split_path))


def signals(sessions, calendar, events):
    """Only known past close and current 09:59 close determine signal membership."""
    rows = []
    dates = sorted(calendar)
    for index, date in enumerate(dates):
        if index == 0 or calendar[date]['close_minute'] != 960:
            rows.append(dict(date=date, status='warmup' if index == 0 else 'excluded_official_half_day'))
            continue
        previous = dates[index - 1]
        prior = sessions.get(previous, {}).get(calendar[previous]['close_minute'] - 1)
        morning = sessions.get(date, {}).get(599)
        if prior is None or morning is None:
            rows.append(dict(date=date, status='unknown_signal_input'))
            continue
        ratio = math.prod(e['ratio'] for e in events if previous < e['ex_date'] <= date)
        adjusted_previous = prior[3] / ratio
        rows.append(dict(date=date, status='known_signal', morning_return=morning[3] / adjusted_previous - 1,
                         previous_date=previous, previous_close=adjusted_previous))
    return rows


def trade_path(bars, cost_bps, entry_minute):
    if (cost_bps, entry_minute) not in [(10, 931), (20, 931), (10, 932)]:
        raise ValueError('Unregistered case')
    price = bars.get(914)
    first = bars.get(entry_minute)
    if price is None or first is None:
        return None
    cost = cost_bps / 10000
    raw = first[0]
    entry = raw * (1 + cost)
    limit = price[3] * 1.001
    result = dict(filled=entry <= limit, entry=entry, limit=limit, stop=raw * .99,
                  entry_minute=entry_minute, cost=cost)
    if not result['filled']:
        return result
    for minute in range(entry_minute, 955):
        bar = bars.get(minute)
        if bar is None:
            return None
        if bar[2] <= result['stop']:
            return dict(result, exit=min(bar[0], result['stop']) * (1 - cost),
                        exit_minute=minute, reason='stop')
    if 955 not in bars:
        return None
    return dict(result, exit=bars[955][0] * (1 - cost), exit_minute=955, reason='scheduled_exit')


def evaluate(rows, sessions, cost_bps, entry_minute, control=False):
    equity = peak = 100000.
    daily, trades, unknown = [], [], []
    permanent = False
    for row in rows:
        date = row['date']
        start = equity
        if row['status'] in ['warmup', 'excluded_official_half_day']:
            daily.append(dict(date=date, status=row['status'], active=False, pnl=0., equity=equity))
            continue
        if row['status'] != 'known_signal':
            unknown.append(dict(date=date, status=row['status']))
            break
        permitted = not permanent and (control or row['morning_return'] > 0)
        outcome = trade_path(sessions.get(date, {}), cost_bps, entry_minute) if permitted else {'filled': False}
        if outcome is None:
            unknown.append(dict(date=date, status='unknown_selected_outcome'))
            break
        qty = 0
        pnl = 0.
        reserved = 0.
        if outcome['filled']:
            risk = outcome['entry'] - outcome['stop'] * (1 - outcome['cost'])
            qty = math.floor(min(start * .01 / outcome['limit'], start * .05 / outcome['limit'],
                                 start * .0005 / risk, start / outcome['limit']))
            if qty > 0:
                reserved = qty * outcome['limit']
                for minute in range(entry_minute, outcome['exit_minute']):
                    adverse = start + qty * (sessions[date][minute][2] * (1 - outcome['cost']) - outcome['entry'])
                    if adverse <= start * .99 or adverse <= peak * .9 or adverse <= 90000:
                        next_bar = sessions[date].get(minute + 1)
                        if next_bar is None:
                            unknown.append(dict(date=date, status='unknown_account_guard_execution'))
                            break
                        outcome = dict(outcome, exit=next_bar[0] * (1 - outcome['cost']),
                                       exit_minute=minute + 1, reason='account_guard')
                        permanent = permanent or adverse <= peak * .9 or adverse <= 90000
                        break
                if unknown:
                    break
                pnl = qty * (outcome['exit'] - outcome['entry'])
                trades.append(dict(date=date, symbol='SPY', qty=qty, pnl=pnl, reserved_usd=reserved, **outcome))
        equity += pnl
        peak = max(peak, equity)
        permanent = permanent or equity <= .9 * peak or equity <= 90000
        daily.append(dict(date=date, status='evaluated', active=qty > 0, pnl=pnl, equity=equity,
                          reserved_usd=reserved, permanent_halt=permanent,
                          realized_daily_limit_breach=pnl < -.01 * start))
    active = [d for d in daily if d['active']]
    wins = sum(d['pnl'] > 0 for d in active)
    complete = not unknown
    interval = wilson(wins, len(active))
    rolling_peak = 100000.
    max_drawdown = 0.
    for day in daily:
        rolling_peak = max(rolling_peak, day['equity'])
        max_drawdown = max(max_drawdown, 1 - day['equity'] / rolling_peak)
    return dict(policy='always_long_matched_control' if control else 'positive_morning_signal',
        cost_bps=cost_bps, entry_minute=entry_minute, complete=complete, expected_sessions=len(rows),
        known_prefix_sessions=len(daily), unknown=unknown, active_days=len(active), winning_days=wins,
        losing_days=sum(d['pnl'] < 0 for d in active), breakeven_days=sum(d['pnl'] == 0 for d in active),
        profit_usd=equity - 100000 if complete else None, known_prefix_profit_usd=equity - 100000,
        winning_active_day_pct=100 * wins / len(active) if active and complete else None,
        wilson_interval=interval if complete else None,
        max_drawdown_pct=max_drawdown * 100 if complete else None,
        known_prefix_eod_max_drawdown_pct=max_drawdown * 100,
        observed_target_hit=bool(complete and active and wins / len(active) >= .9 and equity > 100000),
        internal_statistical_screen_pass=bool(complete and len(active) >= 100 and interval[0] >= 90 and equity > 100000),
        internal_statistical_screen_criterion='at_least100_active_days_and_Wilson95_lower_at_least90pct_and_positive_net; not user goal or independence proof',
        independent_validation_pass=False, production_approved=False, orders=False, daily=daily, trades=trades)


def run(data, calendar_path, split_path, output):
    protocol = load_protocol()
    sessions, calendar, events, evidence = load_inputs(data, calendar_path, split_path)
    rows = signals(sessions, calendar, events)
    results = []
    for case in protocol['cases']:
        cost, minute = case['cost_bps_per_side'], case['entry_minute_ny']
        pair = [evaluate(rows, sessions, cost, minute, control) for control in [False, True]]
        results.append(dict(case=case, signal=pair[0], control=pair[1],
            full_calendar_net_difference_usd=pair[0]['profit_usd'] - pair[1]['profit_usd']
            if pair[0]['complete'] and pair[1]['complete'] else None))
    report = dict(status='completed_exposed_exploratory_not_forward', protocol=protocol,
        protocol_sha256=PROTOCOL_SHA, source_sha256=sha(Path(__file__)), evidence=evidence,
        created_utc=datetime.now(timezone.utc).isoformat(), split_events=events, cases=results,
        orders=False, production_approved=False, independent_validation_pass=False,
        limitations=['Exposed revised historical data, no original delivery or independent forward proof',
            'Adaptation differs from paper; long-only, delayed/limited entry, stop and early exit',
            'OHLC fills and10/20bps costs assumed, not actual broker execution',
            'Research sleeve not production allocations; no modification of production risk',
            'Missing selected input stops cumulative ledger; no profit claim beyond known prefix'])
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'results.json').open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    print(json.dumps([dict(case=x['case'], signal={k:x['signal'][k] for k in ['complete','active_days','profit_usd','winning_active_day_pct','unknown']},
                           control={k:x['control'][k] for k in ['complete','active_days','profit_usd','winning_active_day_pct','unknown']}) for x in results]))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=Path('cache/macro_context_sip/SPY.csv'))
    parser.add_argument('--calendar', type=Path, default=Path('research_runs/calendar_regular_context/calendar_receipt.json'))
    parser.add_argument('--splits', type=Path, default=Path('research_runs/late_day_spy_long_v1/corporate_actions_receipt.json'))
    parser.add_argument('--output', type=Path, default=Path('research_runs/late_day_spy_long_v1'))
    parser.add_argument('--collect-split-metadata', action='store_true')
    args = parser.parse_args()
    load_protocol()
    if args.collect_split_metadata:
        collect_splits(args.splits)
    run(args.data, args.calendar, args.splits, args.output)
