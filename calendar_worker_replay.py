"""Reproduce private research inputs, never authenticate transport or trading.

No network calls, fitting, promotion, orders, or unsafe tar extraction. Caller
must separately verify the public packet's timely external upload anchor.
"""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import gzip
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import tarfile
from zoneinfo import ZoneInfo

import pandas as pd
from active_stock_research import SYMBOLS
from causal_opening_inventory import load_observations
from causal_shadow_collector import opening_observations
from calendar_shadow_bundle import infer, load_own_bundle
from prospective_forecast_evidence import digest, source_digest, read_manifest
from research_commitment import validate_packet, timestamp, commitment
from research_evidence_crypto import decrypt_bytes
from research_clock import validate_sample, ClockSkewError
from split_context_audit import events_from_pages

MAX_BYTES = 512*1024*1024
MAX_FILE_BYTES = 128*1024*1024
NY = ZoneInfo('America/New_York')
EXTRA_FILES = {'calendar.json', 'corporate_actions.json', 'prepared.json',
               'opening.json', 'inference.json', 'capture_clock_check.json'}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def private_files(ciphertext, key):
    """Bound decompression before parsing headers; reject links, paths, extras."""
    if not isinstance(ciphertext, bytes) or len(ciphertext) > MAX_BYTES:
        raise ValueError('Bounded ciphertext required')
    compressed = decrypt_bytes(ciphertext, key)
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        expanded = stream.read(MAX_BYTES+1)
    if len(expanded) > MAX_BYTES:
        raise ValueError('Private archive expansion cap exceeded')
    expected = {'private/'+name for name in EXTRA_FILES} | {
        f'private/history/{s}{suffix}' for s in SYMBOLS for suffix in ('.csv', '.metadata.json')}
    files = {}; total = 0
    with tarfile.open(fileobj=io.BytesIO(expanded), mode='r:') as archive:
        for member in archive:
            name = member.name
            if (name not in expected or name in files or not member.isfile()
                    or member.issym() or member.islnk() or member.sparse
                    or '\\' in name or PurePosixPath(name).as_posix() != name
                    or not 0 <= member.size <= MAX_FILE_BYTES):
                raise ValueError('Unexpected, unsafe or duplicate private archive entry')
            total += member.size
            if total > MAX_BYTES:
                raise ValueError('Private archive content cap exceeded')
            reader = archive.extractfile(member)
            value = reader.read(MAX_FILE_BYTES+1)
            if len(value) != member.size:
                raise ValueError('Truncated private archive file')
            files[name] = value
    if set(files) != expected:
        raise ValueError('Exact complete private input inventory required')
    return files


def validate_protocol(packet, envelope, model_dir):
    validate_packet(packet)
    protocol = envelope['protocol']
    if (digest(protocol) != envelope['protocol_sha256'] or packet['kind'] != 'market'
            or packet['protocol_sha256'] != envelope['protocol_sha256']
            or packet['experiment_id'] != protocol['experiment_id']
            or any(protocol.get(k) is not False for k in ('orders', 'production_approved', 'independent_validation_pass'))
            or packet['session_date'] < protocol['forward_start']):
        raise ValueError('Registered market protocol mismatch')
    sources = protocol['source_sha256']
    if not {'calendar_worker_replay.py', 'calendar_shadow_bundle.py', 'research_commitment.py',
            'research_evidence_crypto.py', 'research_clock.py'} <= set(sources):
        raise ValueError('Incomplete registered replay source evidence')
    if any(source_digest(name) != expected for name, expected in sources.items()):
        raise ValueError('Changed registered replay source')
    manifest = read_manifest(Path(model_dir))
    if (packet['model_manifest_sha256'] != protocol['model_manifest_sha256']
            or packet['model_artifact_sha256'] != protocol['model_artifact_sha256']
            or manifest['manifest_sha256'] != packet['model_manifest_sha256']
            or manifest['manifest']['artifact_sha256'] != packet['model_artifact_sha256']
            or manifest['manifest']['forward_start'] != protocol['forward_start']):
        raise ValueError('Registered frozen model binding mismatch')
    opening = datetime.combine(datetime.fromisoformat(packet['session_date']).date(), datetime.min.time(), NY)+timedelta(hours=9, minutes=30)
    if timestamp(protocol['created_utc']) >= opening or timestamp(manifest['manifest']['created_utc']) >= opening:
        raise ValueError('Model or worker protocol was registered after feature session opening')
    load_own_bundle(Path(model_dir))
    return protocol


def compare_predictions(actual, expected):
    if [p['symbol'] for p in actual] != [p['symbol'] for p in expected]:
        raise ValueError('Forecast symbol order/set changed')
    for a, b in zip(actual, expected):
        if set(a['probabilities']) != {'target_004', 'target_010'} or set(b['probabilities']) != set(a['probabilities']):
            raise ValueError('Prediction head schema changed')
        for name, p in a['probabilities'].items():
            q = b['probabilities'][name]
            if (type(p) not in (int, float) or type(q) not in (int, float)
                    or not math.isfinite(p) or not math.isfinite(q) or not 0 <= p <= 1 or not 0 <= q <= 1
                    or not math.isclose(p, q, rel_tol=0, abs_tol=1e-8)):
                raise ValueError('Probabilities not reproduced')


def reproduce(packet, ciphertext, key, protocol_envelope, model_dir, workspace):
    """Only supplied workspace receives validated CSVs; existing paths refused."""
    if not isinstance(ciphertext, bytes) or sha(ciphertext) != packet['private_ciphertext_sha256']:
        raise ValueError('Private ciphertext is not the committed artifact')
    protocol = validate_protocol(packet, protocol_envelope, model_dir)
    files = private_files(ciphertext, key)
    read = lambda name: json.loads(files['private/'+name])
    session = packet['session_date']; received = timestamp(packet['received_utc']); captured = timestamp(packet['captured_utc'])
    prepared = read('prepared.json'); calendar = read('calendar.json'); split = read('corporate_actions.json')
    start = str(datetime.fromisoformat(session).date()-timedelta(days=100))
    expected_refs = {'history/'+s+suffix for s in SYMBOLS for suffix in ('.csv', '.metadata.json')} | {'calendar.json', 'corporate_actions.json'}
    if (prepared['session_date'] != session or prepared['feed'] != 'sip' or prepared['adjustment'] != 'raw'
            or prepared['history_end_exclusive'] != session or set(prepared['files']) != expected_refs
            or any(sha(files['private/'+name]) != value for name, value in prepared['files'].items())):
        raise ValueError('Prepared input receipt chain changed')
    prepared_at = timestamp(prepared['prepared_utc'])
    if prepared_at > received or str(prepared_at.astimezone(NY).date()) != session:
        raise ValueError('Prepared receipt chronology mismatch')
    query = dict(start=start, end=session)
    split_query = dict(symbols=','.join(SYMBOLS), types='forward_split,reverse_split', **query, limit=1000, sort='asc')
    if (calendar['url'] != 'https://paper-api.alpaca.markets/v2/calendar' or calendar['query'] != query
            or split['url'] != 'https://data.alpaca.markets/v1/corporate-actions' or split['query'] != split_query
            or not timestamp(calendar['received_utc']) <= prepared_at
            or not timestamp(split['received_utc']) <= prepared_at):
        raise ValueError('Wrong provider query or receipt chronology')
    pages = split['pages']
    if not isinstance(pages, list) or not 1 <= len(pages) <= 10:
        raise ValueError('Bounded complete split pagination required')
    tokens = [p.get('next_page_token') for p in pages]
    if (tokens[-1] is not None or any(not isinstance(t, str) or not t for t in tokens[:-1])
            or len(set(tokens[:-1])) != len(tokens[:-1])):
        raise ValueError('Incomplete or ambiguous split pagination')
    events = events_from_pages(pages, SYMBOLS)
    if any(not start <= e['ex_date'] <= session or e['process_date'] > session for e in events):
        raise ValueError('Split outside retained query window')
    opening = read('opening.json')
    if timestamp(opening['received_utc']) != received:
        raise ValueError('Current input receipt time differs from public packet')
    current = opening_observations(opening['raw'], session)
    clock = read('capture_clock_check.json')
    checked = timestamp(clock['checked_utc']); remote = timestamp(clock['remote_date_utc']); rtt = clock['rtt_seconds']
    if (clock.get('status') != 'wall_clock_consistent_not_absolute_utc_proof'
            or any(clock.get(k) is not False for k in ('orders', 'timestamp_adjusted', 'independent_timestamp_anchor'))
            or not 0 <= (received-checked).total_seconds() <= 5):
        raise ValueError('Missing or stale capture clock consistency receipt')
    try:
        checked_sample = validate_sample(format_datetime(remote, usegmt=True), checked-timedelta(seconds=rtt), checked,
            0., rtt, tolerance=clock['tolerance_seconds'])
    except ClockSkewError:
        raise ValueError('Retained clock receipt is inconsistent') from None
    if any(checked_sample[k] != clock[k] for k in
           ('assumed_remote_interval_lower_utc', 'assumed_remote_interval_upper_utc')):
        raise ValueError('Retained clock uncertainty interval changed')
    workspace = Path(workspace)
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError('Existing non-symlink replay workspace required')
    root = workspace.resolve(strict=True)
    target = root/('calendar-replay-'+packet['nonce'])
    target.mkdir(exist_ok=False)
    history = target/'history'; history.mkdir()
    for symbol in SYMBOLS:
        raw = files[f'private/history/{symbol}.csv']
        metadata = json.loads(files[f'private/history/{symbol}.metadata.json'])
        if (metadata.get('symbol') != symbol or metadata.get('start') != start
                or metadata.get('requested_end') != session or metadata.get('feed') != 'sip'
                or metadata.get('adjustment') != 'raw' or metadata.get('sha256') != sha(raw)
                or timestamp(metadata['actual_end']) != timestamp(session+'T00:00:00+00:00')):
            raise ValueError('Historical symbol/feed/window/bytes mismatch')
        frame = pd.read_csv(io.BytesIO(raw))
        stamps = pd.to_datetime(frame.timestamp, utc=True, format='mixed')
        if (set(frame.symbol) != {symbol} or len(frame) != metadata.get('rows') or stamps.isna().any()
                or (stamps < pd.Timestamp(start, tz='UTC')).any()
                or (stamps >= pd.Timestamp(session, tz='UTC')).any()):
            raise ValueError('Historical raw data outside prior-only query')
        for suffix in ('.csv', '.metadata.json'):
            path = history/(symbol+suffix)
            with path.open('xb') as handle:
                handle.write(files['private/history/'+symbol+suffix])
    prior, quality = load_observations(history)
    if quality != prepared['quality'] or any(d >= session for days in prior.values() for d in days):
        raise ValueError('Retained history quality mismatch or future observations')
    combined = {s: dict(prior[s], **{session: current[s]}) for s in SYMBOLS}
    actual = infer(Path(model_dir), combined, events, calendar['rows'], session)
    saved = read('inference.json')
    if (saved.get('session') != session or saved.get('orders') is not False
            or saved.get('production_approved') is not False or saved.get('independent_validation_pass') is not False
            or actual['input_quality'] != saved['input_quality']):
        raise ValueError('Retained input eligibility/inference mismatch')
    compare_predictions(actual['predictions'], saved['predictions'])
    compare_predictions(actual['predictions'], packet['predictions'])
    if [p['signal_price'] for p in actual['predictions']] != [p['signal_price'] for p in saved['predictions']]:
        raise ValueError('Retained signal prices changed')
    return dict(session_date=session, commitment_sha256=commitment(packet),
        private_input_reproduction_verified=True, candidate_symbols=actual['input_quality']['candidate_symbols'],
        predictions=actual['predictions'], transport_anchor_verified=False,
        independent_validation_pass=False, authenticated_forward_observation=False,
        orders=False, production_approved=False,
        limitations=['Private input reproduction is not proof of timely external upload',
                     'HTTP clock consistency is not an independent absolute UTC proof',
                     'Frozen comparators failed explored performance targets; no real fills or approval'])
