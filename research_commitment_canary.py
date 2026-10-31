"""One synthetic dispatch, immutable receipts and bounded read-only polling.

This is an API trust/transport canary, never a market observation. An ambiguous
POST is NEVER retried automatically. Resume only a persisted remote run ID.
"""
import argparse
from datetime import datetime,timedelta,timezone
from email.utils import parsedate_to_datetime
import io
import json
from pathlib import Path,PurePosixPath
import secrets
import time
import zipfile
import requests
import research_commitment as c
from prospective_outcome_audit import BASE,headers,save_once_or_identical

HEAD='080194c4a75422e99ee109c6c0ddba08ceba4fbc'
ACTOR_ID=325262054


def now(): return datetime.now(timezone.utc)


def retain(path,value):
    save_once_or_identical(path,c.canonical(value))


def synthetic_packet(moment,experiment_id='transport_canary_v1',entry_seconds=15):
    return dict(schema=1,kind='synthetic',experiment_id=experiment_id,
        session_date=str(moment.date()),nonce=secrets.token_hex(32),
        protocol_sha256=secrets.token_hex(32),model_manifest_sha256=secrets.token_hex(32),
        model_artifact_sha256=secrets.token_hex(32),private_ciphertext_sha256=secrets.token_hex(32),
        received_utc=moment.isoformat(),captured_utc=moment.isoformat(),
        hypothetical_entry_not_before_utc=(moment+timedelta(seconds=entry_seconds)).isoformat(),
        predictions=[dict(symbol='SYNTH',probabilities=dict(target_004=.5,target_010=.25))],
        orders=False,production_approved=False,independent_validation_pass=False)


def start(output,session=None,*,canary_calibrated=False,experiment_id='transport_canary_v1',entry_seconds=15):
    session=session or requests.Session()
    # No path can silently replay a POST after a timeout/crash.
    if (output/'intent.json').exists(): raise ValueError('Existing dispatch intent: never resend; inspect persisted response')
    started=time.monotonic()
    ref=session.get(BASE+'/git/ref/heads/'+c.BRANCH,headers=headers(),timeout=30)
    finished=time.monotonic()
    ref.raise_for_status()
    if ref.json()['object']['sha']!=HEAD: raise ValueError('Registered anchor branch changed')
    clock=None
    moment=now()
    if canary_calibrated:
        # Synthetic probe ONLY: Date is quantized to a second and generated
        # within the measured request RTT. This is not market receipt timing.
        server=parsedate_to_datetime(ref.headers['Date']).astimezone(timezone.utc)
        clock=dict(scope='SYNTHETIC_CANARY_ONLY_NOT_MARKET',server_date=ref.headers['Date'],
            monotonic_received=finished,round_trip_seconds=finished-started,
            lower_utc=server.isoformat(),upper_utc=(server+timedelta(seconds=1+finished-started)).isoformat(),
            host_observed_utc=moment.isoformat())
        retain(output/'canary_clock.json',clock)
        moment=server+timedelta(seconds=time.monotonic()-finished)
    packet=synthetic_packet(moment,experiment_id,entry_seconds);request=c.dispatch_request(packet)
    retain(output/'intent.json',dict(packet=packet,request=request,expected_head=HEAD,
        expected_actor_id=ACTOR_ID,synthetic=True,market_observations=0,orders=False))
    try:
        response=session.post(request['url'],headers=headers(),json=request['json'],timeout=12)
    except requests.RequestException as exc:
        retain(output/'dispatch_uncertain.json',dict(error_type=type(exc).__name__,retry_allowed=False))
        raise
    retain(output/'dispatch_response.json',dict(status_code=response.status_code,
        server_date=response.headers.get('Date'),body=response.json() if response.content else None))
    response.raise_for_status();data=response.json()
    if type(data.get('workflow_run_id')) is not int: raise ValueError('Direct run ID unavailable; never blindly resend')
    return data['workflow_run_id']


def pre_entry_proof(packet,run,jobs,http_date,received,clock_upper=None):
    c.verify_anchor(packet,run,HEAD,ACTOR_ID)
    entry=c.timestamp(packet['hypothetical_entry_not_before_utc'])
    server=parsedate_to_datetime(http_date).astimezone(timezone.utc)
    # A remote response observed before entry, rather than inference from an
    # artifact produced later. Seconds-resolution Date gets an upper bound.
    not_started=run['status'] in ('queued','pending','waiting','requested') and all(
        j.get('status') in ('queued','pending','waiting','requested') and not j.get('started_at') for j in jobs)
    return bool(server+timedelta(seconds=1)<entry and (clock_upper or received)<entry and not_started)


def verify_artifact(packet,run,metadata,raw,script_sha):
    c.verify_anchor(packet,run,HEAD,ACTOR_ID)
    if metadata.get('workflow_run',{}).get('id')!=run['id'] or metadata.get('expired'):
        raise ValueError('Artifact ownership/availability mismatch')
    if metadata['name']!='research-commitment-'+str(run['id']): raise ValueError('Wrong artifact')
    if metadata.get('digest')!='sha256:'+c.sha(raw): raise ValueError('Remote archive digest mismatch')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)) or sum(x.file_size for x in archive.infolist())>1024*1024:
            raise ValueError('Duplicate or oversized archive')
        if any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts for n in names):
            raise ValueError('Unsafe archive path')
        by_name={PurePosixPath(n).name:archive.read(n) for n in names}
        if len(by_name)!=len(names) or set(by_name)!={'packet.json','dispatch_inputs.json','status.json'}:
            raise ValueError('Exact three public files required')
    if by_name['packet.json']!=c.packet_bytes(packet): raise ValueError('Late packet differs from early commitment')
    inputs=json.loads(by_name['dispatch_inputs.json']);decoded=c.decode_packet(**inputs)
    if decoded!=packet or by_name['dispatch_inputs.json']!=c.canonical(inputs): raise ValueError('Dispatch inputs changed')
    status=json.loads(by_name['status.json'])
    if any(status.get(k) is not False for k in ('orders','production_approved','independent_validation_pass','protocol_accepted')):
        raise ValueError('Unsafe status')
    if (status.get('commitment')!=c.commitment(packet) or status.get('workflow_sha')!=HEAD or
        status.get('workflow_run_id')!=str(run['id']) or status.get('run_attempt')!=1 or
        status.get('script_sha256')!=script_sha or status.get('non_market') is not True or
        status.get('verified_forward_observations')!=0): raise ValueError('Workflow/source/synthetic binding mismatch')
    return dict(artifact_digest=metadata['digest'],artifact_id=metadata['id'],
        artifact_created_after_entry=c.timestamp(metadata['created_at'])>=c.timestamp(packet['hypothetical_entry_not_before_utc']))


def poll(output,session=None):
    session=session or requests.Session();auth=headers()
    intent=json.loads((output/'intent.json').read_bytes());packet=intent['packet']
    run_id=json.loads((output/'dispatch_response.json').read_bytes())['body']['workflow_run_id']
    started=time.monotonic()
    response=session.get(BASE+'/actions/runs/'+str(run_id),headers=auth,timeout=30);response.raise_for_status()
    finished=time.monotonic()
    received=now();run=response.json()
    # Persist every raw run read BEFORE validating it. A transient placeholder
    # title is useful contrary evidence, not a reason to lose the observation.
    observed_name='run_read_'+received.strftime('%Y%m%dT%H%M%S%f')+'.json'
    retain(output/observed_name,dict(run=run,server_date=response.headers.get('Date'),
        received_utc=received.isoformat(),monotonic_received=finished,round_trip_seconds=finished-started))
    c.verify_anchor(packet,run,HEAD,ACTOR_ID)
    jobs_response=session.get(BASE+'/actions/runs/'+str(run_id)+'/jobs',headers=auth,params={'per_page':100},timeout=30)
    jobs_response.raise_for_status();data=jobs_response.json()
    if len(data['jobs'])!=data['total_count']: raise ValueError('Incomplete job observation')
    snapshot=dict(run=run,jobs=data['jobs'],server_date=response.headers.get('Date'),received_utc=received.isoformat(),
        monotonic_received=finished,round_trip_seconds=finished-started)
    name='observation_'+received.strftime('%Y%m%dT%H%M%S%f')+'.json';retain(output/name,snapshot)
    calibrated=(output/'canary_clock.json').exists()
    clock_upper=None
    if calibrated:
        seed=json.loads((output/'canary_clock.json').read_bytes())
        clock_upper=c.timestamp(seed['upper_utc'])+timedelta(seconds=time.monotonic()-seed['monotonic_received'])
        snapshot['canary_only_clock_upper_utc']=clock_upper.isoformat()
    proven=pre_entry_proof(packet,run,data['jobs'],response.headers['Date'],received,clock_upper)
    if proven and not (output/'pre_entry.json').exists(): retain(output/'pre_entry.json',snapshot)
    summary=dict(run_id=run_id,status=run['status'],conclusion=run.get('conclusion'),
        pre_entry_queued_proven=(output/'pre_entry.json').exists(),synthetic_canary_pass=False,
        market_observations=0,independent_validation_pass=False,protocol_accepted=False,orders=False,
        expected_head=HEAD,expected_actor_id=ACTOR_ID,
        trust_scope='GitHub clock/run-name metadata and pinned hosted workflow; not tamper-proof against GitHub/admin censorship')
    if run['status']=='completed':
        if run['conclusion']!='success':
            retain(output/'report.json',summary);return summary
        artifacts=session.get(BASE+'/actions/runs/'+str(run_id)+'/artifacts',headers=auth,timeout=30)
        artifacts.raise_for_status();items=artifacts.json()
        if items['total_count']!=1 or len(items['artifacts'])!=1: raise ValueError('One exact canary archive required')
        meta=items['artifacts'][0];download=session.get(meta['archive_download_url'],headers=auth,timeout=45);download.raise_for_status()
        save_once_or_identical(output/'artifact.zip',download.content);retain(output/'artifact_metadata.json',meta)
        source=session.get(BASE+'/contents/research_commitment.py',headers=auth,params={'ref':HEAD},timeout=30)
        source.raise_for_status()
        import base64
        script_sha=c.sha(base64.b64decode(source.json()['content']).replace(b'\r\n',b'\n'))
        summary.update(verify_artifact(packet,run,meta,download.content,script_sha))
        summary['synthetic_canary_pass']=bool(summary['pre_entry_queued_proven'] and summary['artifact_created_after_entry'])
        retain(output/'report.json',summary)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['start','poll'])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--canary-calibrated',action='store_true')
    parser.add_argument('--experiment-id',default='transport_canary_v1')
    parser.add_argument('--entry-seconds',type=int,default=15)
    parser.add_argument('--observe-seconds',type=int,default=0)
    args=parser.parse_args()
    if args.operation=='start':
        identity=start(args.output,canary_calibrated=args.canary_calibrated,
            experiment_id=args.experiment_id,entry_seconds=args.entry_seconds)
        print(json.dumps(dict(run_id=identity,output=str(args.output))))
    deadline=time.monotonic()+min(max(args.observe_seconds,0),45)
    while True:
        try:
            result=poll(args.output);print(json.dumps(result),flush=True)
            if result['status']=='completed':break
        except ValueError as exc:
            retain(args.output/('rejected_read_'+str(time.monotonic_ns())+'.json'),
                dict(error_type=type(exc).__name__,reason=str(exc),resend=False))
            print(json.dumps(dict(status='read_rejected_no_acceptance',reason=str(exc))),flush=True)
        if time.monotonic()>=deadline:break
        time.sleep(0.2)
