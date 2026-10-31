"""Synthetic private replay fixtures, not authenticated market observations."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
import tarfile

import numpy as np
import pandas as pd
import pytest
import active_stock_research
import calendar_shadow_bundle as bundle
import calendar_worker_replay as replay
import causal_opening_inventory
from causal_shadow_bundle import fit_head
from research_evidence_crypto import encrypt_bytes
from research_clock import validate_sample

KEY = b'k'*32


def encoded(value):
    return json.dumps(value, sort_keys=True, allow_nan=False).encode()


def archive(files, extra=None):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode='w:gz') as tar:
        for name, value in files.items():
            member = tarfile.TarInfo(name); member.size = len(value)
            tar.addfile(member, io.BytesIO(value))
        if extra:
            tar.addfile(extra[0], io.BytesIO(extra[1]))
    return encrypt_bytes(result.getvalue(), KEY)


@pytest.fixture
def fixture(monkeypatch, tmp_path):
    symbols = ['AAPL', 'MSFT']
    for module in (replay, bundle, active_stock_research, causal_opening_inventory):
        monkeypatch.setattr(module, 'SYMBOLS', symbols)
    session = '2026-11-02'; start = '2026-07-25'
    dates = pd.bdate_range(end='2026-10-30', periods=25).strftime('%Y-%m-%d').tolist()
    files = {}; observations = {}; quality = {}
    for symbol in symbols:
        rows = []
        for i, day in enumerate(dates):
            terminal = 779 if day == dates[-1] else 959
            for minute in list(range(570, 600))+[terminal]:
                stamp = pd.Timestamp(day, tz='America/New_York')+pd.Timedelta(minutes=minute)
                price = 100+i*.01
                rows.append(dict(symbol=symbol, timestamp=stamp.tz_convert('UTC').isoformat(),
                    open=price, high=price+.2, low=price-.2, close=price, volume=1000.))
        raw = pd.DataFrame(rows).to_csv(index=False).encode()
        files['private/history/'+symbol+'.csv'] = raw
        files['private/history/'+symbol+'.metadata.json'] = encoded(dict(symbol=symbol, start=start,
            requested_end=session, actual_end=session+'T00:00:00+00:00', feed='sip', adjustment='raw',
            sha256=replay.sha(raw), rows=len(rows)))
        observations[symbol] = {}
        for i, day in enumerate(dates):
            minutes = list(range(570, 600))+[779 if day == dates[-1] else 959]
            observations[symbol][day] = pd.DataFrame(dict(minute=minutes, open=100+i*.01,
                high=100.2+i*.01, low=99.8+i*.01, close=100+i*.01, volume=1000.))
        quality[symbol] = dict(sha256=replay.sha(raw), regular_dates=25)
    calendar = [dict(date=d, open='09:30', close='13:00' if d == dates[-1] else '16:00') for d in dates+[session]]
    files['private/calendar.json'] = encoded(dict(url='https://paper-api.alpaca.markets/v2/calendar',
        query=dict(start=start, end=session), rows=calendar, received_utc=session+'T14:46:00+00:00'))
    files['private/corporate_actions.json'] = encoded(dict(url='https://data.alpaca.markets/v1/corporate-actions',
        query=dict(symbols=','.join(symbols), types='forward_split,reverse_split', start=start,
                   end=session, limit=1000, sort='asc'),
        pages=[dict(corporate_actions=dict(forward_splits=[], reverse_splits=[]), next_page_token=None)],
        received_utc=session+'T14:47:00+00:00'))
    prepared = dict(session_date=session, prepared_utc=session+'T14:48:00+00:00', feed='sip', adjustment='raw',
        history_end_exclusive=session, quality=quality,
        files={name.removeprefix('private/'): replay.sha(raw) for name, raw in files.items()})
    files['private/prepared.json'] = encoded(prepared)
    raw_opening = dict(bars={s: [dict(t=(pd.Timestamp(session+'T09:30', tz='America/New_York')+pd.Timedelta(minutes=i)).isoformat(),
        o=100.25, h=100.45, l=100.05, c=100.25, v=1000.) for i in range(30)] for s in symbols}, next_page_token=None)
    files['private/opening.json'] = encoded(dict(received_utc=session+'T15:15:01+00:00', raw=raw_opening))
    current = replay.opening_observations(raw_opening, session)
    for symbol in symbols:
        observations[symbol][session] = current[symbol]
    rng = np.random.default_rng(19)
    training = [dict(date=f'{i:04}', symbol='AAPL', features=rng.normal(size=16).tolist()) for i in range(90)]
    labels = {(r['date'], r['symbol']): i%2 for i, r in enumerate(training)}
    head = fit_head(training[:30], training[30:], labels)
    model = dict(trained_through='2026-10-01', heads={k:head for k in bundle.TARGETS})
    manifest = dict(forward_start=session, trained_through='2026-10-01', created_utc='2026-10-31T16:20:00+00:00', artifact_sha256='c'*64)
    monkeypatch.setattr(bundle, 'load_own_bundle', lambda directory: (model, manifest))
    monkeypatch.setattr(replay, 'load_own_bundle', lambda directory: (model, manifest))
    monkeypatch.setattr(replay, 'read_manifest', lambda directory: dict(manifest=manifest, manifest_sha256='b'*64))
    result = bundle.infer(tmp_path, observations, [], calendar, session)
    files['private/inference.json'] = encoded(result)
    checked = datetime.fromisoformat(session+'T15:15:00+00:00')
    files['private/capture_clock_check.json'] = encoded(validate_sample('Mon, 02 Nov 2026 15:15:00 GMT',
        checked-timedelta(seconds=.1), checked, 100., 100.1))
    sources = ['calendar_worker_replay.py', 'calendar_shadow_bundle.py', 'research_commitment.py', 'research_clock.py', 'research_evidence_crypto.py']
    protocol = dict(experiment_id='synthetic_replay_test', forward_start=session, created_utc='2026-10-31T17:00:00+00:00',
        model_manifest_sha256='b'*64, model_artifact_sha256='c'*64,
        source_sha256={name: replay.source_digest(name) for name in sources},
        orders=False, production_approved=False, independent_validation_pass=False)
    envelope = dict(protocol=protocol, protocol_sha256=replay.digest(protocol))
    cipher = archive(files)
    packet = dict(schema=1, kind='market', experiment_id=protocol['experiment_id'], session_date=session,
        nonce='a'*64, protocol_sha256=envelope['protocol_sha256'], model_manifest_sha256='b'*64,
        model_artifact_sha256='c'*64, private_ciphertext_sha256=replay.sha(cipher),
        received_utc=session+'T15:15:01+00:00', captured_utc=session+'T15:15:03+00:00',
        hypothetical_entry_not_before_utc=session+'T15:16:00+00:00',
        predictions=[dict(symbol=p['symbol'], probabilities=p['probabilities']) for p in result['predictions']],
        orders=False, production_approved=False, independent_validation_pass=False)
    return files, cipher, packet, envelope


def test_actual_calendar_feature_and_classifier_replay_is_not_transport_evidence(fixture, tmp_path):
    files, cipher, packet, protocol = fixture
    result = replay.reproduce(packet, cipher, KEY, protocol, tmp_path, tmp_path)
    assert result['private_input_reproduction_verified'] is True
    assert result['candidate_symbols'] == ['AAPL', 'MSFT']
    assert not result['independent_validation_pass'] and not result['transport_anchor_verified']
    assert not result['authenticated_forward_observation'] and not result['orders']
    with pytest.raises(FileExistsError):
        replay.reproduce(packet, cipher, KEY, protocol, tmp_path, tmp_path)


def test_cipher_rewrite_and_wrong_key_fail(fixture, tmp_path):
    files, cipher, packet, protocol = fixture
    with pytest.raises(ValueError):
        replay.reproduce(packet, cipher+b'x', KEY, protocol, tmp_path, tmp_path)
    with pytest.raises(Exception):
        replay.reproduce(packet, cipher, b'z'*32, protocol, tmp_path, tmp_path)


def test_future_raw_csv_rejected_even_with_consistent_new_receipt_hashes(fixture, tmp_path):
    files, cipher, packet, protocol = fixture; files = dict(files)
    name = 'private/history/AAPL.csv'
    frame = pd.read_csv(io.BytesIO(files[name]))
    frame.loc[0, 'timestamp'] = '2026-11-02T14:30:00+00:00'
    files[name] = frame.to_csv(index=False).encode()
    meta_name = 'private/history/AAPL.metadata.json'; metadata = json.loads(files[meta_name])
    metadata['sha256'] = replay.sha(files[name]); files[meta_name] = encoded(metadata)
    ready = json.loads(files['private/prepared.json'])
    for key in (name, meta_name):
        ready['files'][key.removeprefix('private/')] = replay.sha(files[key])
    ready['quality']['AAPL']['sha256'] = replay.sha(files[name])
    files['private/prepared.json'] = encoded(ready)
    cipher = archive(files); packet = dict(packet, private_ciphertext_sha256=replay.sha(cipher))
    with pytest.raises(ValueError, match='prior-only'):
        replay.reproduce(packet, cipher, KEY, protocol, tmp_path, tmp_path)


def test_member_size_limit_is_enforced_before_loading_inputs(fixture, tmp_path, monkeypatch):
    files, cipher, packet, protocol = fixture
    monkeypatch.setattr(replay, 'MAX_FILE_BYTES', 10)
    with pytest.raises(ValueError, match='archive entry'):
        replay.reproduce(packet, cipher, KEY, protocol, tmp_path, tmp_path)


@pytest.mark.parametrize('change', ['missing', 'extra', 'path_traversal', 'symlink', 'duplicate'])
def test_archive_allowlist_rejects_unsafe_inventory(fixture, tmp_path, change):
    files, cipher, packet, protocol = fixture
    files = dict(files); extra = None
    if change == 'missing':
        files.pop('private/opening.json')
    elif change == 'extra':
        files['private/secret.env'] = b'not real secrets'
    else:
        member = tarfile.TarInfo('../outside' if change == 'path_traversal' else 'private/opening.json')
        member.size = 0
        if change == 'symlink':
            files.pop('private/opening.json'); member.type = tarfile.SYMTYPE; member.linkname = '/outside'
        extra = (member, b'')
    cipher = archive(files, extra); packet = dict(packet, private_ciphertext_sha256=replay.sha(cipher))
    with pytest.raises(ValueError):
        replay.reproduce(packet, cipher, KEY, protocol, tmp_path, tmp_path)


@pytest.mark.parametrize('change', ['probability', 'modelhash', 'protocolhash', 'sourcehash'])
def test_public_and_protocol_binding_rejected(fixture, tmp_path, change):
    files, cipher, packet, protocol = deepcopy(fixture)
    if change == 'probability':
        packet['predictions'][0]['probabilities']['target_004'] = .999
    elif change == 'modelhash':
        packet['model_manifest_sha256'] = 'f'*64
    elif change == 'protocolhash':
        packet['protocol_sha256'] = 'f'*64
    else:
        protocol['protocol']['source_sha256']['research_clock.py'] = 'f'*64
        protocol['protocol_sha256'] = replay.digest(protocol['protocol'])
        packet['protocol_sha256'] = protocol['protocol_sha256']
    with pytest.raises(ValueError):
        replay.reproduce(packet, cipher, KEY, protocol, tmp_path, tmp_path)


@pytest.mark.parametrize('change', ['missing_opening', 'future_split', 'split_query', 'receipt_hash',
                                  'future_preparation', 'clock_skew', 'wrong_signal'])
def test_private_receipt_or_reproduction_corruption_rejected(fixture, tmp_path, change):
    files, cipher, packet, protocol = fixture; files = dict(files)
    if change == 'missing_opening':
        name = 'private/opening.json'; value = json.loads(files[name]); value['raw']['bars']['AAPL'].pop()
    elif change in ('future_split', 'split_query'):
        name = 'private/corporate_actions.json'; value = json.loads(files[name])
        if change == 'split_query':
            value['query']['end'] = '2026-11-03'
        else:
            value['pages'][0]['corporate_actions']['forward_splits'] = [dict(id='future', symbol='AAPL',
                ex_date='2026-11-03', process_date='2026-11-02', old_rate=1, new_rate=10)]
    elif change in ('receipt_hash', 'future_preparation'):
        name = 'private/prepared.json'; value = json.loads(files[name])
        if change == 'receipt_hash':
            value['files']['calendar.json'] = 'f'*64
        else:
            value['prepared_utc'] = '2026-11-03T15:15:00+00:00'
    elif change == 'clock_skew':
        name = 'private/capture_clock_check.json'; value = json.loads(files[name]); value['remote_date_utc'] = '2026-11-02T15:14:39+00:00'
    else:
        name = 'private/inference.json'; value = json.loads(files[name]); value['predictions'][0]['signal_price'] += 1
    files[name] = encoded(value)
    if name in ('private/corporate_actions.json',):
        ready = json.loads(files['private/prepared.json']); ready['files'][name.removeprefix('private/')] = replay.sha(files[name])
        files['private/prepared.json'] = encoded(ready)
    cipher = archive(files); packet = dict(packet, private_ciphertext_sha256=replay.sha(cipher))
    with pytest.raises(ValueError):
        replay.reproduce(packet, cipher, KEY, protocol, tmp_path, tmp_path)
