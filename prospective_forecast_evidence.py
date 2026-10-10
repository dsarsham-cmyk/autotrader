"""Write-once local evidence boundary for prospective research, NOT trading.

Local clock/hash checks do not provide external timestamp authentication.
Independent evidence requires externally anchored artifacts and actual data
receipt provenance. This utility neither schedules a collector nor fits models.
"""
from datetime import datetime, timezone, date, time, timedelta
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo


def utc_now():
    return datetime.now(timezone.utc)


def timestamp(value):
    parsed=datetime.fromisoformat(value)
    if parsed.tzinfo is None: raise ValueError('Timezone-aware timestamp required')
    return parsed.astimezone(timezone.utc)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_digest(path):
    raw=Path(path).read_bytes()
    if Path(path).suffix=='.py': raw=raw.replace(b'\r\n',b'\n')
    return hashlib.sha256(raw).hexdigest()


def source_matches(manifest):
    hash_function=source_digest if manifest.get('source_hash_format')=='python_lf_normalized' else file_digest
    return all(hash_function(path)==value for path,value in manifest['source_sha256'].items())


def write_once(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    encoded=json.dumps(value,indent=2,sort_keys=True,allow_nan=False)
    # Exclusive creation rejects retries that could overwrite old evidence.
    with path.open('x',encoding='utf-8') as handle:
        handle.write(encoded)


def freeze(directory,artifact_path,source_paths,trained_through,forward_start,feed='sip',information_delay=15,
           source_root=None,history_provenance_required=False):
    now=utc_now()
    train=date.fromisoformat(trained_through)
    start=date.fromisoformat(forward_start)
    local_today=now.astimezone(ZoneInfo('America/New_York')).date()
    if train>=start or train>local_today or start<=local_today:
        raise ValueError('Training must precede a strictly future forward start')
    if feed not in {'sip','iex'} or not isinstance(information_delay,int) or isinstance(information_delay,bool) or not 0<=information_delay<=60:
        raise ValueError('Invalid matched-feed timing protocol')
    if feed=='sip' and information_delay<15:
        raise ValueError('Current SIP protocol requires at least 15 assumed delay minutes')
    if not source_paths: raise ValueError('Frozen forecast source evidence required')
    refs={str(Path(p).resolve().relative_to(Path(source_root).resolve())).replace('\\','/')
          if source_root else str(Path(p).resolve()):source_digest(p) for p in source_paths}
    artifact_hash=file_digest(artifact_path)
    manifest=dict(schema=1,created_utc=now.isoformat(),trained_through=trained_through,
        forward_start=forward_start,feed=feed,feature_cutoff_minute=30,
        information_delay_minutes=information_delay,execution_latency_minutes=1,
        artifact_sha256=artifact_hash,source_sha256=refs,source_hash_format='python_lf_normalized',
        history_provenance_required=history_provenance_required,
        research_only=True,broker_orders_enabled=False,production_approved=False,
        required_external_timestamp_anchor=True)
    envelope=dict(manifest=manifest,manifest_sha256=digest(manifest))
    write_once(Path(directory)/'manifest.json',envelope)
    return envelope


def read_manifest(directory):
    envelope=json.loads((Path(directory)/'manifest.json').read_text(encoding='utf-8'))
    manifest=envelope['manifest']
    if digest(manifest)!=envelope['manifest_sha256']:
        raise ValueError('Manifest integrity mismatch')
    if not manifest.get('research_only') or manifest.get('broker_orders_enabled') is not False or manifest.get('production_approved') is not False:
        raise ValueError('Not a research-only manifest')
    return envelope


def capture(directory,artifact_path,session_date,input_receipt,predictions):
    """Caller must retain raw feed response and actual receipt timestamp.

    Predictions contain symbol, probability, mean_return and q10_return.
    No caller-supplied issued_at is accepted; capture uses the current clock.
    Whole forecast packet is recorded once per experiment/date, even abstention.
    """
    now=utc_now()
    envelope=read_manifest(directory)
    manifest=envelope['manifest']
    session=date.fromisoformat(session_date)
    if session.weekday()>=5 or session<date.fromisoformat(manifest['forward_start']):
        raise ValueError('Not an eligible prospective weekday session')
    # Weekday is not a holiday calendar: caller must supply official calendar
    # evidence for a real exchange session, retained and externally auditable.
    if input_receipt.get('calendar_session_date')!=session_date:
        raise ValueError('Matching exchange-calendar session evidence required')
    if date.fromisoformat(manifest['trained_through'])>=session:
        raise ValueError('Training overlaps prospective session')
    cutoff=datetime.combine(session,time(9,30),ZoneInfo('America/New_York'))+timedelta(minutes=manifest['feature_cutoff_minute'])
    available=cutoff+timedelta(minutes=manifest['information_delay_minutes'])
    deadline=available+timedelta(minutes=manifest['execution_latency_minutes'])
    if not available<=now<deadline:
        raise ValueError('Outside prospective capture window; no backdated forecast allowed')
    if timestamp(manifest['created_utc'])>=cutoff:
        raise ValueError('Manifest was not frozen before feature cutoff')
    if input_receipt.get('feed')!=manifest['feed']:
        raise ValueError('Training/inference feed mismatch')
    if timestamp(input_receipt['feature_cutoff_utc'])!=cutoff.astimezone(timezone.utc):
        raise ValueError('Wrong feature cutoff')
    observed=timestamp(input_receipt['last_bar_end_utc'])
    received=timestamp(input_receipt['received_utc'])
    if observed!=cutoff.astimezone(timezone.utc) or not available<=received<=now:
        raise ValueError('Incomplete features or invalid data receipt chronology')
    for key in ['raw_response_sha256','calendar_response_sha256']:
        value=input_receipt.get(key,'')
        if len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Missing raw evidence hash')
        path_key=key.replace('_sha256','_path')
        if not input_receipt.get(path_key) or file_digest(input_receipt[path_key])!=value:
            raise ValueError('Raw evidence file missing or does not match hash')
    calendar=json.loads(Path(input_receipt['calendar_response_path']).read_text(encoding='utf-8'))
    if not isinstance(calendar,list) or not any(row.get('date')==session_date for row in calendar):
        raise ValueError('Raw calendar does not contain the requested session')
    raw=json.loads(Path(input_receipt['raw_response_path']).read_text(encoding='utf-8'))
    bars=raw.get('bars',{})
    if raw.get('next_page_token') or not isinstance(bars,dict) or not bars:
        raise ValueError('Complete raw opening-bar packet required')
    opening=cutoff-timedelta(minutes=manifest['feature_cutoff_minute'])
    required_times={opening+timedelta(minutes=i) for i in range(manifest['feature_cutoff_minute'])}
    for symbol,records in bars.items():
        observed_times=[timestamp(row['t']) for row in records]
        if len(observed_times)!=len(required_times) or set(observed_times)!=required_times:
            raise ValueError('Missing, duplicate or future raw opening bars')
    if any(prediction.get('symbol') not in bars for prediction in predictions):
        raise ValueError('Forecast symbol missing from raw observations')
    if file_digest(artifact_path)!=manifest['artifact_sha256']:
        raise ValueError('Frozen model artifact changed')
    if not source_matches(manifest): raise ValueError('Frozen forecast source changed')
    history=input_receipt.get('history_files',{})
    if manifest.get('history_provenance_required') and not history:
        raise ValueError('Historical feature-input provenance required')
    for source,expected in history.items():
        if file_digest(source)!=expected: raise ValueError('Historical feature-input file changed')
    symbols=[]
    for prediction in predictions:
        if set(prediction)!={'symbol','probability','mean_return','q10_return'}:
            raise ValueError('Unknown or missing prediction fields')
        if not isinstance(prediction['symbol'],str) or not prediction['symbol']:
            raise ValueError('Invalid symbol')
        symbols.append(prediction['symbol'])
        for key in ['probability','mean_return','q10_return']:
            if not math.isfinite(prediction[key]): raise ValueError('Nonfinite forecast')
        if not 0<=prediction['probability']<=1: raise ValueError('Invalid probability')
    if len(set(symbols))!=len(symbols): raise ValueError('Duplicate symbol forecast')
    record=dict(session_date=session_date,captured_utc=now.isoformat(),
        hypothetical_entry_not_before_utc=deadline.astimezone(timezone.utc).isoformat(),
        manifest_sha256=envelope['manifest_sha256'],input_receipt=input_receipt,
        predictions=predictions,broker_orders_enabled=False,production_approved=False,
        external_anchor_verified=False)
    packet=dict(record=record,record_sha256=digest(record))
    write_once(Path(directory)/'predictions'/f'{session_date}.json',packet)
    return packet


def inspect(directory):
    envelope=read_manifest(directory)
    records=[]
    for path in sorted((Path(directory)/'predictions').glob('*.json')):
        packet=json.loads(path.read_text(encoding='utf-8'))
        record=packet['record']
        if digest(record)!=packet['record_sha256'] or record['manifest_sha256']!=envelope['manifest_sha256']:
            raise ValueError('Forecast integrity mismatch')
        records.append(record)
    return dict(recorded_sessions=len(records),
        # No external-anchor verification implementation: never infer trust
        # from a caller-editable flag inside local evidence.
        externally_anchored_sessions=0,
        independent_validation_pass=False,broker_orders_enabled=False,
        status='local_prospective_records_not_independently_authenticated')
