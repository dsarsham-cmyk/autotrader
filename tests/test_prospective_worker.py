from datetime import datetime
import json

import pytest
import prospective_worker as worker


class Clock:
    def __init__(self, value='2026-11-02T14:45:00+00:00'):
        self.value = datetime.fromisoformat(value)

    def __call__(self):
        return self.value

    def set(self, value):
        self.value = datetime.fromisoformat(value)


class Adapter:
    def __init__(self):
        self.prepares = self.captures = 0
        self.closed = False
        self.late = False

    def prepare(self, session, path):
        self.prepares += 1
        return None if self.closed else {'session': session}

    def restore(self, session, path):
        return None

    def capture(self, session, prepared, path, clock):
        self.captures += 1
        received = clock()
        return [dict(symbol='AAPL', probabilities=dict(target_004=.6, target_010=.2))], received, clock()

    def seal(self, path):
        return b'synthetic-encrypted-private-data'


def make(tmp_path, sender=None):
    clock, adapter, sent = Clock(), Adapter(), []
    protocol = dict(forward_start='2026-11-02', experiment_id='unit_test',
        protocol_sha256='a'*64, model_manifest_sha256='b'*64, model_artifact_sha256='c'*64)
    def send(packet):
        sent.append(packet)
        return {'run_id': 123}
    instance = worker.Worker(protocol, tmp_path, adapter, sender or send, clock,
        clock_check=lambda: {'synthetic_clock_fixture': True})
    return instance, clock, adapter, sent


@pytest.mark.parametrize('moment,state', [
    ('2026-10-31T14:45:00+00:00', 'not_scheduled'),
    ('2026-11-02T14:44:59+00:00', 'waiting'),
    ('2026-11-02T14:45:00+00:00', 'preparation'),
    ('2026-11-02T15:15:00+00:00', 'capture'),
    ('2026-11-02T15:16:00+00:00', 'missed_window'),
])
def test_ny_window_dst_weekend_and_deadline(moment, state):
    assert worker.phase(datetime.fromisoformat(moment), '2026-11-02')[1] == state
    with pytest.raises(ValueError, match='Aware'):
        worker.phase(datetime(2026, 11, 2), '2026-11-02')


def test_once_capture_is_pending_not_validated_and_restart_does_not_retry(tmp_path):
    instance, clock, adapter, sent = make(tmp_path)
    assert instance.tick()['status'] == 'prepared_waiting_for_capture'
    instance.tick()
    assert adapter.prepares == 1
    clock.set('2026-11-02T15:15:02+00:00')
    status = instance.tick()
    assert status['status'] == 'captured_anchor_pending'
    assert not status['authenticated_forward_observation']
    assert len(sent) == 1 and sent[0]['orders'] is False
    assert len(sent[0]['nonce']) == 64
    packet = json.loads((tmp_path/'2026-11-02/packet.json').read_text())
    assert 'synthetic-encrypted-private-data' not in json.dumps(packet)
    resumed = worker.Worker(instance.protocol, tmp_path, adapter, instance.sender, clock,
        clock_check=instance.clock_check)
    resumed.tick()
    assert adapter.captures == len(sent) == 1


def test_uncertain_dispatch_remains_uncertain_after_restart(tmp_path):
    def sender(packet):
        raise TimeoutError('no secrets in status')
    instance, clock, adapter, _ = make(tmp_path, sender)
    instance.tick(); clock.set('2026-11-02T15:15:02+00:00')
    assert instance.tick()['status'] == 'dispatch_uncertain_requires_reconciliation'
    assert instance.tick()['status'] == 'dispatch_uncertain_requires_reconciliation'
    assert adapter.captures == 1


def test_no_preparation_no_late_download_and_no_backfill(tmp_path):
    instance, clock, adapter, sent = make(tmp_path)
    clock.set('2026-11-02T15:15:02+00:00')
    assert instance.tick()['status'] == 'missed_preparation_no_late_download'
    clock.set('2026-11-02T15:16:00+00:00')
    assert instance.tick()['status'] == 'missed_window'
    assert adapter.prepares == adapter.captures == len(sent) == 0
    assert not (tmp_path/'2026-11-02/claim.json').exists()


def test_encryption_crossing_deadline_never_dispatches(tmp_path):
    instance, clock, adapter, sent = make(tmp_path)
    instance.tick(); clock.set('2026-11-02T15:15:58+00:00')
    def seal(path):
        clock.set('2026-11-02T15:16:00+00:00')
        return b'encrypted'
    adapter.seal = seal
    assert instance.tick()['status'] == 'failed_no_forward_claim'
    assert sent == []
    assert (tmp_path/'2026-11-02/claim.json').exists()
    assert not (tmp_path/'2026-11-02/packet.json').exists()


def test_exchange_closed_is_not_active_or_a_win(tmp_path):
    instance, clock, adapter, sent = make(tmp_path)
    adapter.closed = True
    result = instance.tick()
    assert result['status'] == 'exchange_closed'
    assert result['authenticated_forward_observation'] is False
    assert sent == []


def test_stale_lock_filename_does_not_mean_live_worker(tmp_path):
    path = tmp_path/'worker.lock'
    path.write_bytes(b'old')
    with worker.process_lock(path):
        with pytest.raises(OSError):
            with worker.process_lock(path):
                pass
    with worker.process_lock(path):
        pass


def test_write_once_never_overwrites_packet(tmp_path):
    path = tmp_path/'packet.json'
    worker.write_once(path, {'first': True})
    with pytest.raises(FileExistsError):
        worker.write_once(path, {'first': False})
    assert json.loads(path.read_text()) == {'first': True}


def test_clock_failure_blocks_before_provider_call_or_claim(tmp_path):
    from research_clock import ClockSkewError
    instance, clock, adapter, sent = make(tmp_path)
    def fail():
        raise ClockSkewError('inconsistent UTC')
    instance.clock_check = fail
    assert instance.tick()['status'] == 'clock_unverified_no_forecast'
    clock.set('2026-11-02T15:15:02+00:00')
    assert instance.tick()['status'] == 'clock_unverified_no_forecast'
    assert adapter.prepares == adapter.captures == len(sent) == 0
    assert not (tmp_path/'2026-11-02/claim.json').exists()


def test_prepared_wait_does_not_burn_unauthenticated_clock_api_quota(tmp_path):
    instance, clock, adapter, sent = make(tmp_path)
    checks = []
    instance.clock_check = lambda: checks.append(1) or {'synthetic_clock_fixture': True}
    for _ in range(60):
        instance.tick()
    assert len(checks) == adapter.prepares == 1


def test_clock_failure_before_dispatch_never_sends(tmp_path):
    instance, clock, adapter, sent = make(tmp_path)
    instance.tick(); clock.set('2026-11-02T15:15:02+00:00')
    calls = []
    def check():
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError('clock drift after capture')
        return {'synthetic_clock_fixture': True}
    instance.clock_check = check
    assert instance.tick()['status'] == 'failed_no_forward_claim'
    assert adapter.captures == 1 and sent == []


@pytest.mark.parametrize('corruption', ['none', 'feed', 'adjustment', 'end', 'future_preparation',
    'quality', 'missing_file', 'changed_file', 'current_history'])
def test_restored_provider_inputs_must_reproduce_complete_prior_provenance(tmp_path, monkeypatch, corruption):
    import active_stock_research as stocks
    import causal_opening_inventory as inventory
    monkeypatch.setattr(stocks, 'SYMBOLS', ['AAPL'])
    private = tmp_path/'private'
    names = ['history/AAPL.csv', 'history/AAPL.metadata.json', 'calendar.json', 'corporate_actions.json']
    for name in names:
        path = private/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('fixture')
    quality = {'rows': 30}
    prior = {'AAPL': {'2026-10-30': object()}}
    monkeypatch.setattr(inventory, 'load_observations', lambda _: (prior, quality))
    monkeypatch.setattr(worker, 'now', lambda: datetime.fromisoformat('2026-11-02T15:15:00+00:00'))
    ready = dict(session_date='2026-11-02', prepared_utc='2026-11-02T14:50:00+00:00',
        feed='sip', adjustment='raw', history_end_exclusive='2026-11-02', quality=quality,
        files={worker.Path(name).as_posix(): worker.digest_file(private/name) for name in names})
    if corruption == 'feed': ready['feed'] = 'iex'
    elif corruption == 'adjustment': ready['adjustment'] = 'all'
    elif corruption == 'end': ready['history_end_exclusive'] = '2026-11-03'
    elif corruption == 'future_preparation': ready['prepared_utc'] = '2026-11-02T15:16:00+00:00'
    elif corruption == 'quality': ready['quality'] = {'rows': 31}
    elif corruption == 'missing_file': ready['files'].pop(worker.Path('history/AAPL.csv').as_posix())
    elif corruption == 'changed_file': (private/'history/AAPL.csv').write_text('different')
    elif corruption == 'current_history': prior['AAPL']['2026-11-02'] = object()
    (private/'prepared.json').write_text(json.dumps(ready))
    adapter = worker.CalendarAdapter(tmp_path/'unused_model')
    if corruption == 'none':
        assert adapter.restore('2026-11-02', private)[0] is prior
    else:
        with pytest.raises(ValueError):
            adapter.restore('2026-11-02', private)
