"""Experimental public commitments, NOT approved forward evidence or orders.

Trust assumptions: GitHub's API clock/run metadata, hosted runner and pinned
workflow/actions are honest. A late artifact alone never proves early content.
The proposed binding is SHA256(packet) in the server-rendered run name. Its
creation-time behavior must first be demonstrated by a non-market canary.
Deletion/administrator censorship and long-term private-archive availability
are not solved here. No automatic protocol or trading approval is possible.
"""
import argparse
import base64
import binascii
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo

REPOSITORY='dsarsham-cmyk/autotrader'
BRANCH='research-anchor-v1'
WORKFLOW='.github/workflows/research-commitment.yml'
PREFIX='AT-anchor-v1:'
MAX_ENCODED=60000
KEYS={'schema','kind','experiment_id','session_date','nonce','protocol_sha256',
      'model_manifest_sha256','model_artifact_sha256','private_ciphertext_sha256',
      'received_utc','captured_utc','hypothetical_entry_not_before_utc','predictions',
      'orders','production_approved','independent_validation_pass'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(packet):
    return json.dumps(packet,sort_keys=True,separators=(',',':'),
                      ensure_ascii=True,allow_nan=False).encode('ascii')


def packet_bytes(packet):
    validate_packet(packet)
    return canonical(packet)


def commitment(packet):
    return sha(packet_bytes(packet))


def timestamp(value):
    if not isinstance(value,str): raise ValueError('Timestamp must be a string')
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset()!=timedelta(0):
        raise ValueError('UTC aware timestamp required')
    return parsed


def hash_value(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):
        raise ValueError('Lowercase SHA256 required')


def validate_packet(packet):
    if not isinstance(packet,dict) or set(packet)!=KEYS:
        raise ValueError('Public packet allowlist required; no raw inputs or credentials')
    if type(packet['schema']) is not int or packet['schema']!=1:
        raise ValueError('Unsupported commitment schema')
    kind=packet['kind']
    if kind not in ('synthetic','market'):
        raise ValueError('Unsupported research mode')
    if any(packet[k] is not False for k in ('orders','production_approved','independent_validation_pass')):
        raise ValueError('Research safety flags must be false')
    if not isinstance(packet['experiment_id'],str) or not re.fullmatch('[a-z][a-z0-9_-]{0,47}',packet['experiment_id']):
        raise ValueError('Restricted experiment identifier required')
    if not isinstance(packet['nonce'],str) or not re.fullmatch('[0-9a-f]{64}',packet['nonce']):
        raise ValueError('256-bit nonce required')
    date=packet['session_date']
    if not isinstance(date,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date):
        raise ValueError('Canonical session date required')
    datetime.strptime(date,'%Y-%m-%d')
    for name in ('protocol_sha256','model_manifest_sha256','model_artifact_sha256','private_ciphertext_sha256'):
        hash_value(packet[name])
    received,captured,entry=[timestamp(packet[k]) for k in
        ('received_utc','captured_utc','hypothetical_entry_not_before_utc')]
    if not received<=captured<entry:
        raise ValueError('Receive/capture outside before-entry interval')
    if kind=='market':
        cutoff=datetime.fromisoformat(date+'T10:00:00').replace(tzinfo=ZoneInfo('America/New_York'))
        available=cutoff+timedelta(minutes=15)
        if entry!=available+timedelta(minutes=1) or received<available:
            raise ValueError('Unchanged NY10:00 cutoff,15-minute information delay and one-minute execution latency required')
    predictions=packet['predictions']
    if not isinstance(predictions,list) or len(predictions)>100:
        raise ValueError('Bounded public predictions required')
    seen=set()
    for prediction in predictions:
        if not isinstance(prediction,dict) or set(prediction)!={'symbol','probabilities'}:
            raise ValueError('Only symbol and probabilities may be public')
        symbol=prediction['symbol']
        if not isinstance(symbol,str) or not re.fullmatch('[A-Z][A-Z0-9.]{0,9}',symbol) or symbol in seen:
            raise ValueError('Unique restricted symbols required')
        seen.add(symbol)
        values=prediction['probabilities']
        if not isinstance(values,dict) or set(values)!={'target_004','target_010'}:
            raise ValueError('Both fixed prediction heads required')
        for head,probability in values.items():
            if not re.fullmatch('[a-z][a-z0-9_]{0,31}',head):
                raise ValueError('Restricted prediction head required')
            if type(probability) not in (int,float) or not math.isfinite(probability) or not 0<=probability<=1:
                raise ValueError('Finite probability required')
    return packet


def encode_packet(packet):
    validate_packet(packet)
    raw=canonical(packet);encoded=base64.b64encode(raw).decode('ascii')
    if len(encoded)>MAX_ENCODED: raise ValueError('Packet exceeds dispatch budget')
    return dict(packet_b64=encoded,commitment=sha(raw))


def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError('Duplicate JSON key')
        result[key]=value
    return result


def decode_packet(packet_b64,commitment):
    encoded=packet_b64
    hash_value(commitment)
    if not isinstance(encoded,str) or not 0<len(encoded)<=MAX_ENCODED:
        raise ValueError('Bounded Base64 required')
    try:
        raw=base64.b64decode(encoded,validate=True)
        if base64.b64encode(raw).decode('ascii')!=encoded: raise ValueError('Noncanonical Base64')
        packet=json.loads(raw.decode('ascii'),object_pairs_hook=unique_object)
    except (binascii.Error,UnicodeError,json.JSONDecodeError) as exc:
        raise ValueError('Invalid encoded public packet') from exc
    validate_packet(packet)
    if raw!=canonical(packet) or sha(raw)!=commitment:
        raise ValueError('Canonical packet/commitment mismatch')
    return packet


def dispatch_request(packet,ref=BRANCH):
    """Build only; caller owns authorization and transport. Never sends a POST."""
    if ref!=BRANCH: raise ValueError('Registered anchor branch required')
    return dict(url=f'https://api.github.com/repos/{REPOSITORY}/actions/workflows/research-commitment.yml/dispatches',
                json=dict(ref=ref,inputs=encode_packet(packet),return_run_details=True))


def verify_anchor(packet,run,expected_head,expected_actor_id,repository=REPOSITORY):
    """Metadata consistency, never independent validation or protocol approval."""
    validate_packet(packet)
    packet_commitment=commitment(packet)
    if not isinstance(expected_head,str) or not re.fullmatch('[0-9a-f]{40}',expected_head):
        raise ValueError('Pre-registered source commit required')
    if repository!=REPOSITORY or run.get('repository',{}).get('full_name')!=repository or run.get('path')!=WORKFLOW:
        raise ValueError('Wrong repository/workflow')
    actor_id=run.get('actor',{}).get('id')
    if type(expected_actor_id) is not int or expected_actor_id<=0 or type(actor_id) is not int or actor_id!=expected_actor_id:
        raise ValueError('Pre-registered dispatch actor required')
    if run.get('event')!='workflow_dispatch' or type(run.get('run_attempt')) is not int or run['run_attempt']!=1:
        raise ValueError('Original dispatch attempt required; reruns rejected')
    if run.get('head_sha')!=expected_head or run.get('head_branch')!=BRANCH:
        raise ValueError('Registered head SHA and branch required')
    if type(run.get('id')) is not int or run['id']<=0:
        raise ValueError('Remote run identity required')
    if run.get('display_title')!=PREFIX+packet_commitment:
        raise ValueError('Server-rendered commitment title mismatch')
    created=timestamp(run.get('created_at'));entry=timestamp(packet['hypothetical_entry_not_before_utc'])
    upper=created+timedelta(seconds=1)
    # API seconds are a quantized interval, not exact subsecond timestamps.
    if not timestamp(packet['captured_utc'])<=upper or not upper<entry:
        raise ValueError('Remote creation not conservatively before entry')
    return dict(status='experimental_metadata_consistency_only',run_id=run['id'],
        commitment=packet_commitment,session_date=packet['session_date'],experiment_id=packet['experiment_id'],
        non_market=packet['kind']=='synthetic',timing_consistent=True,
        creation_upper_bound_utc=upper.isoformat(),protocol_accepted=False,
        verified_forward_observation=False,independent_validation_pass=False,orders=False,
        production_approved=False,
        limitation='Requires canary proof of creation-time binding, fixed workflow/artifact audit and private-input reproduction')


def verify_series(records,*,expected_head,expected_actor_id,discovery_complete):
    if discovery_complete is not True: raise ValueError('Complete dispatch discovery required')
    dates=set();nonces=set();run_ids=set();reports=[]
    for record in records:
        packet=decode_packet(record['packet_b64'],record['commitment'])
        report=verify_anchor(packet,record['run'],expected_head,expected_actor_id)
        key=(packet['experiment_id'],packet['session_date'])
        if key in dates or packet['nonce'] in nonces or report['run_id'] in run_ids:
            raise ValueError('Duplicate dispatch/session/nonce; no retrospective selection or retry observation')
        dates.add(key);nonces.add(packet['nonce']);run_ids.add(report['run_id']);reports.append(report)
    return dict(status='experimental_commitment_series_only',records=reports,
        verified_forward_observations=0,protocol_accepted=False,independent_validation_pass=False,orders=False)


def record_event(event_path,output):
    """Trusted fixed workflow entry point. Copies validated event data, no shell."""
    event=json.loads(event_path.read_bytes(),object_pairs_hook=unique_object)
    inputs=event.get('inputs')
    if not isinstance(inputs,dict) or set(inputs)!={'packet_b64','commitment'}:
        raise ValueError('Only registered dispatch inputs allowed')
    packet=decode_packet(inputs['packet_b64'],inputs['commitment'])
    if os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch' or os.environ.get('GITHUB_RUN_ATTEMPT')!='1':
        raise ValueError('Only initial workflow dispatch accepted')
    if os.environ.get('GITHUB_REPOSITORY')!=REPOSITORY or os.environ.get('GITHUB_REF')!='refs/heads/'+BRANCH:
        raise ValueError('Unexpected workflow execution origin')
    output.mkdir(parents=True,exist_ok=True)
    (output/'packet.json').write_bytes(canonical(packet))
    (output/'dispatch_inputs.json').write_bytes(canonical(inputs))
    status=dict(status='experimental_commitment_recorded_not_forward_validation',
        commitment=inputs['commitment'],non_market=packet['kind']=='synthetic',
        recorded_utc=datetime.now(timezone.utc).isoformat(),workflow_sha=os.environ.get('GITHUB_SHA'),
        workflow_run_id=os.environ.get('GITHUB_RUN_ID'),run_attempt=1,
        script_sha256=sha(Path(__file__).read_bytes().replace(b'\r\n',b'\n')),
        verified_forward_observations=0,protocol_accepted=False,independent_validation_pass=False,
        orders=False,production_approved=False)
    (output/'status.json').write_bytes(canonical(status))
    return status


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('research_runs/commitment'))
    args=parser.parse_args()
    record_event(Path(os.environ['GITHUB_EVENT_PATH']),args.output)
