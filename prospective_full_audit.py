"""Reproduce frozen forecasts from authenticated encrypted inputs, then audit.

GET-only data access. No model promotion, orders, refitting or risk changes.
Only genuinely prospective packets count as such; fixtures never become data.
"""
import argparse
from datetime import datetime,time,timedelta,timezone
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import tarfile
import zipfile
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import sklearn
from dotenv import load_dotenv

from active_stock_research import SYMBOLS,load_universe
from prospective_model_collector import current_context,get_json
from prospective_forecast_evidence import read_manifest,file_digest,source_matches,timestamp
from regime_predictive_research import predict_forecasters,EXTRA_FEATURES
from predictive_portfolio_research import FEATURES
from prospective_outcome_audit import inspect_run,verify_archive,save_once_or_identical,evaluate_simulated_session
from research_evidence_crypto import MAGIC,evidence_key,decrypt_bytes


def decrypt_private_archive(encrypted):
    if not encrypted.startswith(MAGIC):
        raise ValueError('Dedicated v2 encryption required; broker-derived envelopes rejected')
    plaintext=decrypt_bytes(encrypted,evidence_key())
    files={};total=0
    with tarfile.open(fileobj=io.BytesIO(plaintext),mode='r:gz') as archive:
        for member in archive:
            name=PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or not member.isfile():
                raise ValueError('Unsafe or nonregular private archive member')
            total+=member.size
            if total>512*1024*1024 or member.name in files:
                raise ValueError('Oversized or duplicate private evidence')
            files[member.name]=archive.extractfile(member).read()
    return files


def retained_file(files,original_path,expected_hash):
    base=PurePosixPath(original_path.replace('\\','/')).name
    matches=[value for name,value in files.items() if PurePosixPath(name).name==base]
    if len(matches)!=1 or hashlib.sha256(matches[0]).hexdigest()!=expected_hash:
        raise ValueError('Missing, ambiguous or changed retained input')
    return matches[0]


def reproduce(packet,files,model_dir,work):
    envelope=read_manifest(model_dir);manifest=envelope['manifest']
    if not source_matches(manifest): raise ValueError('Use the frozen forecast sources for reproducibility')
    model_path=model_dir/'model.joblib'
    if file_digest(model_path)!=manifest['artifact_sha256']: raise ValueError('Frozen artifact changed')
    artifact=joblib.load(model_path)  # Own artifact checked before loading.
    if artifact.get('sklearn_version')!=sklearn.__version__ or artifact.get('features')!=FEATURES+EXTRA_FEATURES:
        raise ValueError('Model runtime/schema mismatch')
    if artifact.get('mode')!='prospective_research_control_only' or artifact.get('broker_orders_enabled') is not False:
        raise ValueError('Not a research-only model')
    record=packet['record'];receipt=record['input_receipt'];session=record['session_date']
    raw=json.loads(retained_file(files,receipt['raw_response_path'],receipt['raw_response_sha256']))
    calendar=json.loads(retained_file(files,receipt['calendar_response_path'],receipt['calendar_response_sha256']))
    if not any(row.get('date')==session for row in calendar): raise ValueError('Wrong retained calendar session')
    history=receipt.get('history_files',{})
    if len(history)!=len(SYMBOLS): raise ValueError('Complete historical context required')
    names={PurePosixPath(path.replace('\\','/')).name for path in history}
    if names!={symbol+'.csv' for symbol in SYMBOLS}: raise ValueError('Historical universe mismatch')
    directory=work/'history'/session
    for original,expected in history.items():
        raw_csv=retained_file(files,original,expected)
        save_once_or_identical(directory/PurePosixPath(original.replace('\\','/')).name,raw_csv)
    prior,_=load_universe(directory)
    if not prior or any(date>=session for date in prior): raise ValueError('History is not strictly prior')
    opening=datetime.combine(datetime.fromisoformat(session).date(),time(9,30),ZoneInfo('America/New_York'))
    expected_times=[opening+timedelta(minutes=i) for i in range(30)]
    current={}
    if raw.get('next_page_token'): raise ValueError('Retained raw opening packet incomplete')
    for symbol,records in raw['bars'].items():
        records=sorted(records,key=lambda row:row['t'])
        if [timestamp(row['t']) for row in records]!=expected_times:
            raise ValueError('Invalid or future retained opening timestamps')
        current[symbol]=np.array([[row[key] for key in ['o','h','l','c','v']] for row in records])
    rows=current_context(prior,current,session)
    recomputed=predict_forecasters(artifact['fitted'],rows)
    published={p['symbol']:p for p in record['predictions']}
    if len(published)!=len(record['predictions']) or set(published)!=set(SYMBOLS):
        raise ValueError('Missing or duplicate published forecasts')
    for index,row in enumerate(rows):
        for key,values in recomputed.items():
            if not np.isclose(values[index],published[row['symbol']][key],rtol=0,atol=1e-8):
                raise ValueError('Published prediction is not reproduced from retained inputs')
    return raw


def completed_market_data(session,work):
    date=datetime.fromisoformat(session).date()
    opening=datetime.combine(date,time(9,30),ZoneInfo('America/New_York'))
    close=datetime.combine(date,time(16),ZoneInfo('America/New_York'))
    if datetime.now(timezone.utc)<close+timedelta(minutes=16):
        raise ValueError('Completed delayed-SIP outcome not available yet')
    raw=get_json('https://data.alpaca.markets/v2/stocks/bars',dict(symbols=','.join(SYMBOLS),
        timeframe='1Min',feed='sip',adjustment='raw',limit=10000,
        start=opening.astimezone(timezone.utc).isoformat(),
        end=(close-timedelta(microseconds=1)).astimezone(timezone.utc).isoformat()))
    if raw.get('next_page_token'): raise ValueError('Incomplete full-session outcome pagination')
    expected=[opening+timedelta(minutes=i) for i in range(390)]
    arrays={}
    if set(raw.get('bars',{}))!=set(SYMBOLS): raise ValueError('Missing full-session outcome symbols')
    for symbol,records in raw['bars'].items():
        records=sorted(records,key=lambda row:row['t'])
        if [timestamp(row['t']) for row in records]!=expected:
            raise ValueError('Incomplete, duplicated or wrong-session outcome bars')
        arrays[symbol]=np.array([[row[key] for key in ['o','h','l','c','v']] for row in records])
    encoded=json.dumps(raw,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    save_once_or_identical(work/'market_data'/f'{session}.json',encoded)
    return arrays,hashlib.sha256(encoded).hexdigest()


def load_verified_sessions(run_id,backup,model_dir):
    """GET/digest/decrypt/reproduce chain; accepted arrays are research inputs.

    Late anchors are exclusions, not inactive days. This function does not
    evaluate profits or reset capital, allowing one cumulative series replay.
    """
    envelope=read_manifest(model_dir)
    inspection=inspect_run(run_id,backup,envelope)
    work=backup/str(run_id);packets=[];ciphertexts=[]
    for artifact_id in inspection['retained_artifacts']:
        meta=json.loads((work/f'{artifact_id}.metadata.json').read_text())
        content=(work/f'{artifact_id}.zip').read_bytes();verify_archive(meta,content)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for name in archive.namelist():
                if '/predictions/' in name and name.endswith('.json'):
                    packets.append((json.loads(archive.read(name)),meta))
                elif name.endswith('private_evidence.aesgcm'):
                    ciphertexts.append(archive.read(name))
    accepted=[];excluded=[]
    by_hash={a['record_sha256']:a for a in inspection['anchors']}
    timely=[]
    for packet,meta in packets:
        anchor=by_hash[packet['record_sha256']]
        if not anchor['timely_external_anchor']:
            excluded.append(dict(session_date=packet['record']['session_date'],status='excluded_late_external_anchor'))
        else:
            timely.append((packet,dict(meta,verified_upload_completed_at=anchor['artifact_upload_completed_utc'])))
    if timely:
        if len(ciphertexts)!=1: raise ValueError('One authenticated private input archive required')
        files=decrypt_private_archive(ciphertexts[0])
        for packet,meta in timely:
            opening=reproduce(packet,files,model_dir,work)
            completed,market_hash=completed_market_data(packet['record']['session_date'],work)
            accepted.append(dict(packet=packet,metadata=meta,raw_opening=opening,
                completed_bars=completed,outcome_sip_sha256=market_hash,
                input_predictions_reproduced=True,run_id=run_id))
    return inspection,accepted,excluded


def audit_run(run_id,backup,model_dir):
    envelope=read_manifest(model_dir)
    inspection,accepted,excluded=load_verified_sessions(run_id,backup,model_dir)
    work=backup/str(run_id)
    report=dict(run_id=run_id,forecast_packets=inspection['forecast_packets'],sessions=[],excluded=excluded,orders=False,
        independent_validation_pass=False,production_approved=False,
        status='no_prospective_forecasts' if not inspection['forecast_packets'] else 'future_outcome_audit')
    for bundle in accepted:
        result=evaluate_simulated_session(bundle['packet'],bundle['metadata'],envelope,
            bundle['raw_opening'],bundle['completed_bars'])
        result.update(input_predictions_reproduced=True,outcome_sip_sha256=bundle['outcome_sip_sha256'])
        report['sessions'].append(result)
    (work/'full_audit.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(dict(run_id=run_id,forecast_packets=inspection['forecast_packets'],evaluated_sessions=len(report['sessions']),
        independent_validation_pass=False,orders=False)))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',type=int,required=True)
    parser.add_argument('--backup',type=Path,default=Path('research_runs/prospective_backups'))
    parser.add_argument('--model-dir',type=Path,default=Path('research_prospective/control_v2'))
    args=parser.parse_args();load_dotenv();audit_run(args.run_id,args.backup,args.model_dir)
