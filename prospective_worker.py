"""Separate persistent research collector. No order API or model promotion.

Nothing starts at import. Capture is once per NY date, never after the window;
GitHub dispatch acceptance is only anchor-pending, not authenticated evidence.
The old Actions experiments and their missing dates are never rewritten.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, time, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import tarfile
import time as timer
from zoneinfo import ZoneInfo


NY = ZoneInfo('America/New_York')
REPOSITORY = 'dsarsham-cmyk/autotrader'
WORKFLOW = 'research-commitment.yml'


def now():
    return datetime.now(timezone.utc)


def digest_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_digest(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()
    with path.open('xb') as handle:
        handle.write(data)


def phase(moment, forward_start):
    if moment.tzinfo is None:
        raise ValueError('Aware clock required')
    local = moment.astimezone(NY)
    session = str(local.date())
    available = datetime.combine(local.date(), time(10, 15), NY)
    deadline = available + timedelta(minutes=1)
    if local.weekday() >= 5 or session < forward_start:
        value = 'not_scheduled'
    elif moment < available - timedelta(minutes=30):
        value = 'waiting'
    elif moment < available:
        value = 'preparation'
    elif moment < deadline:
        value = 'capture'
    else:
        value = 'missed_window'
    return session, value, available, deadline


@contextmanager
def process_lock(path):
    """OS-released lock: an old filename alone never denotes a live worker."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        handle.seek(0)
        if not handle.read(1):
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            lock = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            unlock = lambda: (handle.seek(0), msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1))
        else:
            import fcntl
            lock = lambda: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            unlock = lambda: fcntl.flock(handle, fcntl.LOCK_UN)
        lock()
        try:
            yield
        finally:
            unlock()


def checked_clock():
    from research_clock import verify_remote_clock, require_fresh
    return require_fresh(verify_remote_clock())


class Worker:
    def __init__(self, protocol, work, adapter, sender, clock=now, clock_check=checked_clock):
        self.protocol, self.work = protocol, Path(work)
        self.adapter, self.sender, self.clock = adapter, sender, clock
        self.clock_check = clock_check
        self.prepared = None
        self.clock_retry_after = 0.

    def status(self, session, state, **fields):
        result = dict(session_date=session, status=state,
            updated_utc=self.clock().isoformat(), orders=False,
            production_approved=False, independent_validation_pass=False,
            authenticated_forward_observation=False, **fields)
        path = self.work / 'status.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(result, indent=2, allow_nan=False))
        temporary.replace(path)
        return result

    def tick(self):
        with process_lock(self.work / 'worker.lock'):
            return self._tick()

    def _tick(self):
        session, current, available, deadline = phase(self.clock(), self.protocol['forward_start'])
        day = self.work / session
        if (day / 'claim.json').exists():
            # Never silently retry a capture or an uncertain POST after restart.
            state = ('captured_anchor_pending' if (day / 'dispatch.json').exists() else
                     'dispatch_uncertain_requires_reconciliation' if (day / 'dispatch_started.json').exists()
                     else 'claimed_requires_reconciliation')
            return self.status(session, state)
        if current in ('waiting', 'not_scheduled', 'missed_window'):
            return self.status(session, current)
        if current == 'preparation' and self.prepared is not None and self.prepared[0] == session:
            return self.status(session, 'prepared_waiting_for_capture')
        if timer.monotonic() < self.clock_retry_after:
            return self.status(session, 'clock_unverified_no_forecast', clock_retry_cooldown=True)
        try:
            clock_sample = self.clock_check()
        except Exception as error:
            self.clock_retry_after = timer.monotonic() + 300
            return self.status(session, 'clock_unverified_no_forecast', error_type=type(error).__name__)
        # A slow clock probe cannot turn an expired window into a capture.
        if phase(self.clock(), self.protocol['forward_start'])[1] == 'missed_window':
            return self.status(session, 'missed_window')
        if current == 'preparation':
            prepared = self.adapter.prepare(session, day / 'private')
            if prepared is None:
                return self.status(session, 'exchange_closed')
            self.prepared = (session, prepared)
            return self.status(session, 'prepared_waiting_for_capture')
        if self.prepared is None or self.prepared[0] != session:
            restored = self.adapter.restore(session, day / 'private')
            if restored is None:
                return self.status(session, 'missed_preparation_no_late_download')
            self.prepared = (session, restored)
        nonce = secrets.token_hex(32)
        write_once(day / 'claim.json', dict(session_date=session, nonce=nonce,
            claimed_utc=self.clock().isoformat(), protocol_sha256=self.protocol['protocol_sha256']))
        try:
            predictions, received, inference_done = self.adapter.capture(
                session, self.prepared[1], day / 'private', self.clock)
            if not available <= received <= inference_done < deadline:
                raise ValueError('Capture exceeded information/entry boundary')
            write_once(day / 'private' / 'capture_clock_check.json', clock_sample)
            encrypted = self.adapter.seal(day / 'private')
            write_once(day / 'private.aesgcm', encrypted)
            captured = self.clock()
            if not inference_done <= captured < deadline:
                raise ValueError('Encryption missed entry deadline')
            packet = dict(schema=1, kind='market', experiment_id=self.protocol['experiment_id'],
                session_date=session, nonce=nonce, protocol_sha256=self.protocol['protocol_sha256'],
                model_manifest_sha256=self.protocol['model_manifest_sha256'],
                model_artifact_sha256=self.protocol['model_artifact_sha256'],
                private_ciphertext_sha256=hashlib.sha256(encrypted).hexdigest(),
                received_utc=received.astimezone(timezone.utc).isoformat(),
                captured_utc=captured.astimezone(timezone.utc).isoformat(),
                hypothetical_entry_not_before_utc=deadline.astimezone(timezone.utc).isoformat(),
                predictions=predictions, orders=False, production_approved=False,
                independent_validation_pass=False)
            from research_commitment import validate_packet
            validate_packet(packet)
            write_once(day / 'packet.json', packet)
            dispatch_clock = self.clock_check()
            write_once(day / 'dispatch_clock_check.json', dispatch_clock)
            if self.clock() >= deadline:
                raise ValueError('No late dispatch')
            # From this point every exception is uncertain: reconcile, do not POST again.
            write_once(day / 'dispatch_started.json', dict(started_utc=self.clock().isoformat()))
            try:
                response = self.sender(packet)
            except Exception:
                return self.status(session, 'dispatch_uncertain_requires_reconciliation')
            write_once(day / 'dispatch.json', response)
            return self.status(session, 'captured_anchor_pending')
        except Exception as error:
            return self.status(session, 'failed_no_forward_claim', error_type=type(error).__name__)


class CalendarAdapter:
    """Market endpoints are GET-only; private provider bytes never enter packet."""
    def __init__(self, model_dir):
        self.model_dir = Path(model_dir)

    def restore(self, session, private):
        from active_stock_research import SYMBOLS
        from causal_opening_inventory import load_observations
        private = Path(private)
        receipt = private / 'prepared.json'
        if not receipt.exists():
            return None
        ready = json.loads(receipt.read_text())
        expected = {(Path('history') / (s + suffix)).as_posix() for s in SYMBOLS
                    for suffix in ('.csv', '.metadata.json')} | {'calendar.json', 'corporate_actions.json'}
        prepared_at = datetime.fromisoformat(ready['prepared_utc'])
        if (prepared_at.tzinfo is None or prepared_at > now() or
                str(prepared_at.astimezone(NY).date()) != session or
                ready['session_date'] != session or ready['feed'] != 'sip' or
                ready['adjustment'] != 'raw' or ready['history_end_exclusive'] != session or
                set(ready['files']) != expected or any((private / name).is_symlink() or
                digest_file(private / name) != sha for name, sha in ready['files'].items())):
            raise ValueError('Changed prepared input receipt')
        prior, quality = load_observations(private / 'history')
        if (quality != ready['quality'] or set(prior) != set(SYMBOLS) or
                any(d >= session for days in prior.values() for d in days)):
            raise ValueError('Restored history provenance/quality mismatch')
        return prior, ready

    def prepare(self, session, private):
        from concurrent.futures import ThreadPoolExecutor
        from active_stock_research import SYMBOLS, fetch_symbol
        from causal_opening_inventory import load_observations
        from causal_shadow_collector import split_pages
        from prospective_model_collector import get_json
        from calendar_shadow_bundle import load_own_bundle
        load_own_bundle(self.model_dir)
        private = Path(private)
        receipt = private / 'prepared.json'
        restored = self.restore(session, private)
        if restored is not None:
            return restored
        start = str(datetime.fromisoformat(session).date() - timedelta(days=100))
        calendar = get_json('https://paper-api.alpaca.markets/v2/calendar', dict(start=start, end=session))
        calendar_received = now().isoformat()
        if not any(row['date'] == session for row in calendar):
            return None
        history = private / 'history'
        history.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda symbol: fetch_symbol(symbol, history, start, session), SYMBOLS))
        prior, quality = load_observations(history)
        if any(d >= session for days in prior.values() for d in days):
            raise ValueError('Prior-only history required')
        actions = split_pages(get_json, session, start)
        write_once(private / 'calendar.json', dict(url='https://paper-api.alpaca.markets/v2/calendar',
            query=dict(start=start, end=session), rows=calendar, received_utc=calendar_received))
        write_once(private / 'corporate_actions.json', dict(url='https://data.alpaca.markets/v1/corporate-actions',
            query=dict(symbols=','.join(SYMBOLS), types='forward_split,reverse_split',
                       start=start, end=session, limit=1000, sort='asc'),
            pages=actions, received_utc=now().isoformat()))
        files = {path.relative_to(private).as_posix(): digest_file(path)
                 for path in private.rglob('*') if path.is_file()}
        ready = dict(session_date=session, prepared_utc=now().isoformat(), files=files,
            feed='sip', adjustment='raw', history_end_exclusive=session, quality=quality)
        write_once(receipt, ready)
        return prior, ready

    def capture(self, session, prepared, private, clock):
        from active_stock_research import SYMBOLS
        from causal_shadow_collector import opening_observations
        from calendar_shadow_bundle import infer
        from prospective_model_collector import get_json
        from split_context_audit import events_from_pages
        prior, ready = prepared
        if any(digest_file(private / name) != sha for name, sha in ready['files'].items()):
            raise ValueError('Prepared data changed before inference')
        opening = datetime.combine(datetime.fromisoformat(session).date(), time(9, 30), NY)
        raw = get_json('https://data.alpaca.markets/v2/stocks/bars', dict(
            symbols=','.join(SYMBOLS), timeframe='1Min', feed='sip', adjustment='raw', limit=10000,
            start=opening.astimezone(timezone.utc).isoformat(),
            end=(opening + timedelta(minutes=30, microseconds=-1)).astimezone(timezone.utc).isoformat()))
        received = clock()
        current = opening_observations(raw, session)
        observations = {s: dict(prior[s], **{session: current[s]}) for s in SYMBOLS}
        calendar = json.loads((private / 'calendar.json').read_text())['rows']
        events = events_from_pages(json.loads((private / 'corporate_actions.json').read_text())['pages'], SYMBOLS)
        result = infer(self.model_dir, observations, events, calendar, session)
        write_once(private / 'opening.json', dict(received_utc=received.isoformat(), raw=raw))
        write_once(private / 'inference.json', result)
        predictions = [dict(symbol=p['symbol'], probabilities=p['probabilities']) for p in result['predictions']]
        return predictions, received, clock()

    def seal(self, private):
        from research_evidence_crypto import encrypt_bytes, evidence_key
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w:gz') as tar:
            for path in sorted(private.rglob('*')):
                if path.is_file():
                    tar.add(path, arcname=(Path('private') / path.relative_to(private)).as_posix(), recursive=False)
        return encrypt_bytes(archive.getvalue(), evidence_key())


def github_sender(protocol):
    """No credential helper fallback in an unattended cloud service."""
    def send(packet):
        import requests
        from research_commitment import dispatch_request
        request = dispatch_request(packet)
        token = os.environ['AUTOTRADER_RESEARCH_GITHUB_TOKEN']
        response = requests.post(request['url'],
            headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json'},
            json=request['json'],
            timeout=15, allow_redirects=False)
        if response.status_code != 200:
            raise RuntimeError('Dispatch response not confirmed; reconcile without retry')
        data = response.json()
        return dict(run_details=data, status='dispatch_received_not_anchor_verified')
    return send


def register_protocol(path, model_dir, anchor_head_sha, actor_id, canary_report):
    """Registration is local-only, future-only, immutable and never promotion."""
    import re
    from prospective_forecast_evidence import digest, read_manifest
    from calendar_shadow_bundle import load_own_bundle
    path, model_dir = Path(path), Path(model_dir)
    if path.exists() or not re.fullmatch('[0-9a-f]{40}', anchor_head_sha):
        raise ValueError('New protocol path and fixed anchor commit required')
    if type(actor_id) is not int or actor_id <= 0:
        raise ValueError('Registered actor identity required')
    _, parent = load_own_bundle(model_dir)
    envelope = read_manifest(model_dir)
    created = now()
    if parent['forward_start'] <= str(created.astimezone(NY).date()):
        raise ValueError('Strictly future cohort required; old gaps remain missing')
    canary = json.loads(Path(canary_report).read_text())
    if (canary.get('timely_artifact_anchor_verified') is not True or
            canary.get('authenticated_api_reads_verified') is not True or canary.get('kind') != 'synthetic' or
            canary.get('head_sha') != anchor_head_sha or canary.get('actor_id') != actor_id or
            canary.get('market_observations') != 0):
        raise ValueError('Verified strict pre-entry-upload synthetic transport probe required')
    sources = worker_source_closure() + ['requirements-calendar-worker.txt']
    protocol = dict(schema=1, experiment_id='calendar_shadow_reliable_v1',
        created_utc=created.isoformat(), forward_start=parent['forward_start'],
        model_manifest_sha256=envelope['manifest_sha256'], model_artifact_sha256=parent['artifact_sha256'],
        source_sha256={name: source_digest(name) for name in sources},
        anchor_head_sha=anchor_head_sha, actor_id=actor_id,
        anchor_method='successful_artifact_upload_before_entry_plus_one_second_margin',
        run_creation_only_anchor_accepted=False,
        anchor_script_sha256=canary['script_sha256'], anchor_workflow_sha256=canary['workflow_sha256'],
        canary_report_sha256=digest_file(canary_report),
        orders=False, production_approved=False, independent_validation_pass=False,
        prior_exploration_failed_target=True, private_archive_backup_configured=False)
    result = dict(protocol=protocol, protocol_sha256=digest(protocol))
    write_once(path, result)
    return result


def worker_source_closure():
    import ast
    pending = ['prospective_worker.py', 'calendar_worker_replay.py', 'research_commitment_upload_audit.py']
    found = set()
    while pending:
        name = pending.pop()
        if name in found:
            continue
        found.add(name)
        tree = ast.parse(Path(name).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            modules = ([node.module] if isinstance(node, ast.ImportFrom) and node.module else
                       [n.name for n in node.names] if isinstance(node, ast.Import) else [])
            for module in modules:
                local = module.split('.')[0] + '.py'
                if Path(local).is_file() and local not in found:
                    pending.append(local)
    return sorted(found)


def load_protocol(path, model_dir):
    from prospective_forecast_evidence import digest, read_manifest
    envelope = json.loads(Path(path).read_text())
    protocol = envelope['protocol']
    if digest(protocol) != envelope['protocol_sha256']:
        raise ValueError('Worker protocol digest mismatch')
    if set(protocol['source_sha256']) != set(worker_source_closure() + ['requirements-calendar-worker.txt']):
        raise ValueError('Complete worker source closure required')
    if any(source_digest(name) != sha for name, sha in protocol['source_sha256'].items()):
        raise ValueError('Changed registered worker source')
    validate_worker_runtime()
    parent = read_manifest(Path(model_dir))
    if (parent['manifest_sha256'] != protocol['model_manifest_sha256'] or
            parent['manifest']['artifact_sha256'] != protocol['model_artifact_sha256'] or
            parent['manifest']['forward_start'] != protocol['forward_start'] or
            protocol['orders'] is not False or protocol['production_approved'] is not False):
        raise ValueError('Worker/model protocol mismatch')
    from calendar_shadow_bundle import load_own_bundle
    load_own_bundle(Path(model_dir))
    return dict(protocol, protocol_sha256=envelope['protocol_sha256'])


def validate_worker_runtime(path=Path('requirements-calendar-worker.txt')):
    import importlib.metadata
    import re
    for line in path.read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)', line)
        if not match or importlib.metadata.version(match[1]) != match[2]:
            raise ValueError('Exact research-only runtime required')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['register', 'plan', 'once', 'serve'])
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--work', type=Path, default=Path('research_runs/calendar_worker'))
    parser.add_argument('--canary-report', type=Path)
    parser.add_argument('--anchor-head')
    parser.add_argument('--actor-id', type=int)
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv()
    if args.mode == 'register':
        if not args.canary_report or not args.anchor_head or not args.actor_id:
            parser.error('register requires canary report, anchor head and actor id')
        register_protocol(args.protocol, args.model_dir, args.anchor_head, args.actor_id, args.canary_report)
        print(json.dumps(dict(status='registered_research_only_not_deployed', orders=False)))
        return
    protocol = load_protocol(args.protocol, args.model_dir)
    if args.mode == 'plan':
        session, state, available, deadline = phase(now(), protocol['forward_start'])
        print(json.dumps(dict(session_date=session, state=state, available=available.isoformat(),
            deadline=deadline.isoformat(), orders=False, production_approved=False)))
        return
    worker = Worker(protocol, args.work, CalendarAdapter(args.model_dir), github_sender(protocol))
    while True:
        try:
            result = worker.tick()
        except Exception as error:
            result = worker.status(str(now().astimezone(NY).date()), 'preparation_failed_no_forecast',
                                   error_type=type(error).__name__)
        print(json.dumps(result), flush=True)
        if args.mode == 'once':
            return
        timer.sleep(1 if phase(now(), protocol['forward_start'])[1] == 'capture' else 30)


if __name__ == '__main__':
    main()
