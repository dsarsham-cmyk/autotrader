"""Calendar-correct frozen comparators, never trading approval or backfill."""
import argparse
import ast
from datetime import date
import importlib.metadata
import json
from pathlib import Path
import platform
from zoneinfo import ZoneInfo

import joblib
import numpy as np
from threadpoolctl import threadpool_limits
from active_stock_research import SYMBOLS
from balanced_target_simulator import path
from calendar_regular_context import calendar_lookup, calendar_opening_rows, clip_sessions, URL
from causal_opening_inventory import FEATURES, load_observations
from causal_shadow_bundle import fit_head, predict_head
from causal_sparse_research import market_maps, partition
import prospective_forecast_evidence as evidence
from split_context_audit import events_from_pages, iso_date
from split_predictive_research import flatten

MODE = 'calendar_correct_shadow_only_v1'
TARGETS = {'target_004': .004, 'target_010': .01}
PACKAGES = ('numpy', 'pandas', 'scipy', 'scikit-learn', 'joblib', 'threadpoolctl',
            'requests', 'python-dotenv', 'alpaca-py', 'cryptography', 'PyYAML')


def runtime_lock():
    return dict(python=platform.python_version(), packages={p: importlib.metadata.version(p) for p in PACKAGES})


def source_closure(root=None):
    """Seal local transitive imports, including guarded imports, not just facade."""
    root = Path.cwd() if root is None else Path(root)
    pending = ['calendar_shadow_bundle.py']; found = set()
    while pending:
        name = pending.pop()
        if name in found:
            continue
        found.add(name)
        tree = ast.parse((root/name).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            modules = ([node.module] if isinstance(node, ast.ImportFrom) and node.module
                       else [n.name for n in node.names] if isinstance(node, ast.Import) else [])
            for module in modules:
                local = module.split('.')[0]+'.py'
                if (root/local).is_file() and local not in found:
                    pending.append(local)
    return sorted(found)


def opening_inputs(observations, events, calendar_rows, session):
    iso_date(session)
    calendar = calendar_lookup(calendar_rows)
    if session not in calendar or any(d > session for d in calendar):
        raise ValueError('Current and prior-only official calendar required')
    if set(observations) != set(SYMBOLS) or any(d > session for days in observations.values() for d in days):
        raise ValueError('Prior/current-only fixed universe required')
    if any(e['ex_date'] > session for e in events):
        raise ValueError('Future split information forbidden')
    for days in observations.values():
        if session not in days or days[session].minute.tolist() != list(range(570, 600)):
            raise ValueError('Exactly30 current opening bars required')
        for day, frame in days.items():
            values = frame[['open', 'high', 'low', 'close', 'volume']].to_numpy(dtype=float)
            if (frame.minute.duplicated().any() or not frame.minute.is_monotonic_increasing
                    or not np.isfinite(values).all() or (values[:, :4] <= 0).any()
                    or (values[:, 4] < 0).any()
                    or (values[:, 1] < values[:, [0, 2, 3]].max(axis=1)).any()
                    or (values[:, 2] > values[:, [0, 3]].min(axis=1)).any()):
                raise ValueError('Invalid OHLCV/minute history')
        prior_sessions = [d for d in calendar if d < session]
        if not prior_sessions:
            raise ValueError('Prior exchange session required')
        latest = max(prior_sessions)
        terminal = calendar[latest]['close_minute']-1
        if latest not in days or terminal not in set(days[latest].minute):
            raise ValueError('Latest official prior close missing, not an abstention')
    by_date, reasons, applications = calendar_opening_rows(observations, events, calendar)
    rows = flatten({session: by_date.get(session, {})})
    if any(len(r['features']) != 16 or not np.isfinite(r['features']).all() for r in rows):
        raise ValueError('Invalid calendar feature vector')
    return rows, dict(candidate_symbols=[r['symbol'] for r in rows],
        eligibility={s: reasons[(session, s)] for s in SYMBOLS},
        split_applications=[a for a in applications if a['applied_before_session'] == session])


def load_own_bundle(directory):
    directory = Path(directory)
    manifest = evidence.read_manifest(directory)['manifest']
    if (set(manifest['source_sha256']) != set(source_closure())
            or not evidence.source_matches(manifest)
            or evidence.file_digest(directory/'model.joblib') != manifest['artifact_sha256']):
        raise ValueError('Changed own calendar bundle/source closure; not deserialized')
    bundle = joblib.load(directory/'model.joblib')
    if (bundle.get('schema') != 1 or bundle.get('mode') != MODE
            or bundle.get('orders') is not False or bundle.get('production_approved') is not False
            or bundle.get('independent_validation_pass') is not False
            or bundle.get('prior_exploration_failed_target') is not True
            or bundle.get('features') != FEATURES or bundle.get('symbols') != list(SYMBOLS)
            or set(bundle.get('heads', {})) != set(TARGETS)
            or bundle.get('runtime_lock') != runtime_lock()
            or bundle.get('trained_through') != manifest['trained_through']):
        raise ValueError('Incompatible calendar research-only bundle')
    return bundle, manifest


def infer(directory, observations, events, calendar_rows, session):
    bundle, manifest = load_own_bundle(directory)
    if iso_date(session) < manifest['forward_start'] or session <= bundle['trained_through']:
        raise ValueError('No historical backfill or training overlap')
    rows, quality = opening_inputs(observations, events, calendar_rows, session)
    probabilities = {name: predict_head(head, rows) for name, head in bundle['heads'].items()}
    return dict(session=session, predictions=[dict(symbol=r['symbol'], signal_price=r['signal_price'],
        probabilities={name: values[i] for name, values in probabilities.items()}) for i, r in enumerate(rows)],
        input_quality=quality, orders=False, production_approved=False,
        independent_validation_pass=False, authenticated_prospective_evidence=False,
        prior_exploration_failed_target=True)


def verified_training_inputs(data, input_audit, study, split_receipt):
    report = json.loads(Path(input_audit).read_bytes()); reference = json.loads(Path(study).read_bytes())
    receipt_path = Path(input_audit).parent/'calendar_receipt.json'
    if (report['status'] != 'exposed_historical_calendar_input_audit' or report['normal_close_control_exact'] is not True
            or reference['status'] != 'completed_exposed_calendar_predictive_comparison'
            or reference['input_audit_sha256'] != evidence.file_digest(input_audit)
            or report['calendar_receipt_sha256'] != evidence.file_digest(receipt_path)
            or report['split_receipt_sha256'] != evidence.file_digest(split_receipt)):
        raise ValueError('Changed calendar/split/input audit or incomplete exposed study')
    old_reference = Path('research_runs/balanced_target/results.json')
    if reference['reference_sha256'] != evidence.file_digest(old_reference):
        raise ValueError('Changed original matched-target reference')
    old = json.loads(old_reference.read_bytes())
    if any(evidence.source_digest(name) != sha for dependency in
           (old['dependency_sha256'], report['source_sha256'], reference['source_sha256'])
           for name, sha in dependency.items()):
        raise ValueError('Changed audited research source')
    receipt = json.loads(receipt_path.read_bytes()); split = json.loads(Path(split_receipt).read_bytes())
    query = dict(start='2024-01-01', end='2026-10-01')
    split_query = dict(symbols=','.join(SYMBOLS), types='forward_split,reverse_split', **query, limit=1000, sort='asc')
    if (receipt['url'] != URL or receipt['query'] != query
            or split['url'] != 'https://data.alpaca.markets/v1/corporate-actions'
            or split['query'] != split_query or not split['pages'] or split['pages'][-1].get('next_page_token') is not None):
        raise ValueError('Wrong official receipt query or incomplete pagination')
    observations, quality = load_observations(data)
    if quality != report['evidence'] or quality != reference['evidence'] or quality != old['evidence']:
        raise ValueError('Changed historical input bytes')
    expected_cases = {(model, target) for model in ('logistic', 'boosted') for target in TARGETS.values()}
    if (len(reference['cases']) != 4
            or {(c['model'], c['target_fraction']) for c in reference['cases']} != expected_cases
            or any(len(c['outcomes']) != 9 for c in reference['cases'])
            or any(o['target_screen_pass'] is not False or o['full_period_coverage_complete'] is not True
                   for c in reference['cases'] for o in c['outcomes'])):
        raise ValueError('Expected explicitly failed exploratory comparators')
    return observations, quality, receipt['rows'], events_from_pages(split['pages'], list(SYMBOLS))


def fit_heads(rows, market):
    dates = sorted({r['date'] for r in rows})
    if len(dates) <= 60:
        raise ValueError('Distinct training and last60 calibration sessions required')
    heads = {}; counts = {}
    with threadpool_limits(limits=1):
        for name, target in TARGETS.items():
            outcomes = {(r['date'], r['symbol']): path(market.get(r['date'], {}).get(r['symbol'], {}),
                r['signal_price'], target_fraction=target) for r in rows}
            labels = {k: o['label'] for k, o in outcomes.items() if o is not None and o['filled']}
            train, cal = [partition(rows, d) for d in (dates[:-60], dates[-60:])]
            train = [r for r in train if (r['date'], r['symbol']) in labels]
            cal = [r for r in cal if (r['date'], r['symbol']) in labels]
            heads[name] = fit_head(train, cal, labels)
            counts[name] = dict(training_rows=len(train), calibration_rows=len(cal), target_fraction=target)
    return heads, counts, dates


def freeze_bundle(data, directory, input_audit, study, split_receipt, forward_start='2026-11-02'):
    directory = Path(directory); training_end = '2026-10-01'
    if (directory.exists() or iso_date(forward_start) <= training_end
            or forward_start <= str(evidence.utc_now().astimezone(ZoneInfo('America/New_York')).date())):
        raise ValueError('New directory and strictly future forward start required')
    observations, quality, calendar_rows, events = verified_training_inputs(data, input_audit, study, split_receipt)
    if any(d > training_end for days in observations.values() for d in days):
        raise ValueError('Training input crosses fixed training end')
    calendar = calendar_lookup(calendar_rows)
    rows = flatten(calendar_opening_rows(observations, events, calendar)[0])
    dates = sorted({r['date'] for r in rows})
    if len(dates) < 240 or dates[-1] != training_end:
        raise ValueError('Complete fixed training span required')
    heads, counts, dates = fit_heads(rows, market_maps(clip_sessions(observations, calendar)))
    bundle = dict(schema=1, mode=MODE, heads=heads, counts=counts, orders=False, production_approved=False,
        independent_validation_pass=False, prior_exploration_failed_target=True, trained_through=training_end,
        features=FEATURES, symbols=list(SYMBOLS), runtime_lock=runtime_lock(),
        training_last=dates[-61], calibration_first=dates[-60], calibration_last=dates[-1], input_evidence=quality,
        input_audit_sha256=evidence.file_digest(input_audit), study_sha256=evidence.file_digest(study),
        calendar_receipt_sha256=evidence.file_digest(Path(input_audit).parent/'calendar_receipt.json'),
        split_receipt_sha256=evidence.file_digest(split_receipt),
        rule=dict(probability_threshold=.65, cutoff_minute=30, information_delay_minutes=15,
            execution_latency_minutes=1, horizon_minutes=60, stop_fraction=.01, targets=list(TARGETS.values()),
            cost_bps=10, stress_cost_bps=20, stock_cap=.01, category_cap=.05, max_positions=3, planned_trade_risk=.0005))
    directory.mkdir(parents=True)
    joblib.dump(bundle, directory/'model.joblib')
    envelope = evidence.freeze(directory, directory/'model.joblib', source_closure(), training_end, forward_start,
        source_root=Path.cwd(), history_provenance_required=True)
    evidence.write_once(directory/'description.json', dict({k:v for k,v in bundle.items() if k != 'heads'},
        forward_start=forward_start, forward_records=0, original_historical_delivery_authenticated=False,
        limitations=['Exposed failed exploratory models; not independent evidence or an approved profitable strategy',
                    'Actual input receipt and timely external anchor required; never backfill']))
    return bundle, envelope


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--data', type=Path, default=Path('cache/daily_meta_extended'))
    p.add_argument('--directory', type=Path, default=Path('research_prospective/calendar_shadow_v1'))
    p.add_argument('--input-audit', type=Path, default=Path('research_runs/calendar_regular_context/results.json'))
    p.add_argument('--study', type=Path, default=Path('research_runs/calendar_predictive/results.json'))
    p.add_argument('--split-receipt', type=Path, default=Path('research_runs/split_context_audit/corporate_actions_receipt.json'))
    p.add_argument('--forward-start', default='2026-11-02'); a=p.parse_args()
    _, m = freeze_bundle(a.data, a.directory, a.input_audit, a.study, a.split_receipt, a.forward_start)
    print(json.dumps(dict(status='frozen_failed_comparators_only', manifest_sha256=m['manifest_sha256'], orders=False)))
