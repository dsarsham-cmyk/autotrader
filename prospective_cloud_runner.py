"""Isolated cloud research orchestrator; no brokerage writes or model promotion."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,time,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import tarfile
import time as timer
from zoneinfo import ZoneInfo

ROOT=Path('research_prospective/control_v2')
STATUS=Path('research_runs/cloud_status.json')


def now(): return datetime.now(timezone.utc)


def eligible_plan(moment,forward_start):
    local=moment.astimezone(ZoneInfo('America/New_York'))
    cutoff=datetime.combine(local.date(),time(10,15),ZoneInfo('America/New_York'))
    return local.weekday()<5 and str(local.date())>=forward_start and cutoff-timedelta(minutes=30)<=moment<cutoff+timedelta(minutes=1)


def status(value):
    STATUS.parent.mkdir(parents=True,exist_ok=True)
    packet=dict(updated_utc=now().isoformat(),orders=False,production_approved=False,
        workflow_run_id=os.environ.get('GITHUB_RUN_ID'),workflow_sha=os.environ.get('GITHUB_SHA'),**value)
    STATUS.write_text(json.dumps(packet,indent=2,allow_nan=False))
    print(json.dumps(packet),flush=True)
    return packet


def validate():
    import joblib
    import sklearn
    import prospective_forecast_evidence as e
    envelope=e.read_manifest(ROOT)
    manifest=envelope['manifest']
    if not e.source_matches(manifest): raise ValueError('Frozen code mismatch')
    if e.file_digest(ROOT/'model.joblib')!=manifest['artifact_sha256']: raise ValueError('Frozen model mismatch')
    artifact=joblib.load(ROOT/'model.joblib')
    if artifact.get('mode')!='prospective_research_control_only' or artifact.get('sklearn_version')!=sklearn.__version__:
        raise ValueError('Incompatible research control')
    return manifest


def seal_evidence(history,secret):
    # Retain provider data privately. Public artifact carries only authenticated
    # ciphertext; decryption requires the user's existing high-entropy secret.
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    archive=io.BytesIO()
    with tarfile.open(fileobj=archive,mode='w:gz') as tar:
        for directory in [ROOT/'receipts',history]:
            if directory.exists():
                for path in sorted(directory.rglob('*')):
                    if path.is_file(): tar.add(path,arcname=str(path),recursive=False)
    nonce=secrets.token_bytes(12)
    key=hashlib.sha256(b'autotrader-prospective-evidence-v1\0'+secret.encode()).digest()
    aad=b'autotrader-prospective-evidence-v1'
    encrypted=nonce+AESGCM(key).encrypt(nonce,archive.getvalue(),aad)
    path=Path('research_runs/private_evidence.aesgcm')
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(encrypted)
    return hashlib.sha256(encrypted).hexdigest()


def collect_cloud():
    manifest=validate()
    if not eligible_plan(now(),manifest['forward_start']):
        return status(dict(status='skipped_outside_preparation_window',recorded_sessions=0))
    from active_stock_research import SYMBOLS,fetch_symbol
    from prospective_model_collector import collect,get_json
    local=now().astimezone(ZoneInfo('America/New_York'))
    session=str(local.date())
    calendar=get_json('https://paper-api.alpaca.markets/v2/calendar',{'start':session,'end':session})
    if not calendar: return status(dict(status='skipped_exchange_closed',recorded_sessions=0))
    history=Path('cache/cloud_prospective_history')
    history.mkdir(parents=True,exist_ok=True)
    start=str(local.date()-timedelta(days=100))
    # Only strictly prior sessions; feature history is not a retraining step.
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda s:fetch_symbol(s,history,start,session),SYMBOLS))
    target=datetime.combine(local.date(),time(10,15),ZoneInfo('America/New_York'))
    while now()<target:
        timer.sleep(min(30,max(.01,(target-now()).total_seconds())))
    packet=collect(ROOT,history)
    return status(dict(status='forecast_recorded_external_anchor_pending',
        record_sha256=packet['record_sha256'],captured_utc=packet['record']['captured_utc'],
        hypothetical_entry_not_before_utc=packet['record']['hypothetical_entry_not_before_utc'],
        recorded_sessions=1))


def main(mode):
    if mode=='plan':
        manifest=json.loads((ROOT/'manifest.json').read_text())['manifest']
        value=eligible_plan(now(),manifest['forward_start'])
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as handle: handle.write(f'run={str(value).lower()}\n')
        print(json.dumps(dict(run=value,orders=False)))
        return
    try:
        if mode=='validate':
            manifest=validate()
            status(dict(status='cloud_environment_validated_only',manifest_artifact_sha256=manifest['artifact_sha256'],recorded_sessions=0))
        elif mode=='seal':
            value=seal_evidence(Path('cache/cloud_prospective_history'),os.environ['ALPACA_API_SECRET'])
            print(json.dumps(dict(ciphertext_sha256=value,raw_data_published=False)))
        else: collect_cloud()
    except Exception as error:
        status(dict(status='collection_failed_no_forecast_claim',error_type=type(error).__name__,recorded_sessions=0))
        raise RuntimeError('Research task failed; see classified status, no orders issued') from None


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['plan','validate','collect','seal'])
    main(parser.parse_args().mode)
