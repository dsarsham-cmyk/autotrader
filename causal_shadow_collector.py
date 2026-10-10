"""Separate GET-only shadow collector. Never backfill, trade or promote.

Public packets are locally captured predictions, not externally authenticated
evidence until the upload step timestamp is independently checked. Raw inputs
stay private and use the dedicated evidence key, never a broker-secret key.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,time,timezone
import json
import os
from pathlib import Path
import time as timer
from zoneinfo import ZoneInfo
import prospective_forecast_evidence as evidence

ROOT=Path('research_prospective/causal_split_shadow_v1')
HISTORY=Path('cache/causal_shadow_history')
STATUS=Path('research_runs/causal_shadow_cloud_status.json')
SOURCES=['causal_shadow_collector.py','research_evidence_crypto.py','requirements-causal-shadow.txt']


def now(): return datetime.now(timezone.utc)


def timing(session):
    day=datetime.fromisoformat(session).date()
    opening=datetime.combine(day,time(9,30),ZoneInfo('America/New_York'))
    return opening,opening+timedelta(minutes=45),opening+timedelta(minutes=46)


def preparation_window(moment,forward_start):
    if moment.tzinfo is None: raise ValueError('Aware preparation clock required')
    local=moment.astimezone(ZoneInfo('America/New_York'))
    _,available,deadline=timing(str(local.date()))
    return local.weekday()<5 and str(local.date())>=forward_start and available-timedelta(minutes=30)<=moment<deadline


def register(directory):
    from causal_shadow_bundle import load_own_bundle
    _,manifest=load_own_bundle(directory)
    parent=evidence.read_manifest(directory)
    value=dict(schema=1,created_utc=now().isoformat(),parent_manifest_sha256=parent['manifest_sha256'],
        forward_start=manifest['forward_start'],source_sha256={s:evidence.source_digest(s) for s in SOURCES},
        orders=False,production_approved=False,backfill_allowed=False,
        private_inputs_required=True,pre_entry_external_upload_anchor_required=True)
    if value['created_utc']>=timing(manifest['forward_start'])[0].astimezone(timezone.utc).isoformat():
        raise ValueError('Collector must be registered before first feature cutoff')
    packet=dict(protocol=value,protocol_sha256=evidence.digest(value))
    evidence.write_once(directory/'collector_protocol.json',packet)
    print(json.dumps(dict(status='registered_shadow_collector_protocol',protocol_sha256=packet['protocol_sha256'],orders=False)))
    return packet


def validate(directory):
    from causal_shadow_bundle import load_own_bundle
    _,manifest=load_own_bundle(directory)
    packet=json.loads((directory/'collector_protocol.json').read_text())
    p=packet['protocol']
    if (evidence.digest(p)!=packet['protocol_sha256'] or p['parent_manifest_sha256']!=evidence.read_manifest(directory)['manifest_sha256'] or
        p['orders'] is not False or p['production_approved'] is not False or p['backfill_allowed'] is not False or
        p['forward_start']!=manifest['forward_start'] or set(p['source_sha256'])!=set(SOURCES)):
        raise ValueError('Collector protocol mismatch')
    if any(evidence.source_digest(s)!=h for s,h in p['source_sha256'].items()): raise ValueError('Changed collector source')
    if evidence.timestamp(p['created_utc'])>=timing(p['forward_start'])[0]: raise ValueError('Late protocol registration')
    return manifest,packet


def opening_observations(raw,session):
    import pandas as pd
    from active_stock_research import SYMBOLS
    from macro_context_research import proxy_sessions
    opening,_,_=timing(session)
    expected={opening+timedelta(minutes=i) for i in range(30)}
    if raw.get('next_page_token') or set(raw.get('bars',{}))!=set(SYMBOLS): raise ValueError('Complete fixed-universe packet required')
    current={}
    for symbol,records in raw['bars'].items():
        stamps=[evidence.timestamp(r['t']) for r in records]
        if len(stamps)!=30 or set(stamps)!=expected: raise ValueError('Missing, duplicate, future or off-minute bars')
        frame=pd.DataFrame([dict(symbol=symbol,timestamp=r['t'],open=r['o'],high=r['h'],low=r['l'],close=r['c'],volume=r['v']) for r in records])
        sessions=proxy_sessions(frame,symbol)
        if set(sessions)!={session}: raise ValueError('Wrong opening session')
        current[symbol]=sessions[session]
    return current


def calendar_session(rows,session):
    if not isinstance(rows,list) or len(rows)!=1 or rows[0].get('date')!=session or rows[0].get('open')!='09:30':
        raise ValueError('Matching regular-open exchange session required')
    closed=datetime.combine(datetime.fromisoformat(session).date(),time.fromisoformat(rows[0]['close']),ZoneInfo('America/New_York'))
    if closed<=timing(session)[2]+timedelta(minutes=60): raise ValueError('Modeled horizon extends beyond session')


def verify_history_receipt(receipt,session,moment):
    from active_stock_research import SYMBOLS
    if receipt.get('feed')!='sip' or receipt.get('adjustment')!='raw' or receipt.get('end_exclusive')!=session:
        raise ValueError('Historical feed/window mismatch')
    if not evidence.timestamp(receipt['download_started_utc'])<=evidence.timestamp(receipt['prepared_utc'])<=moment:
        raise ValueError('Invalid history receipt chronology')
    for field,suffix in [('history_files','.csv'),('metadata_files','.metadata.json')]:
        refs=receipt.get(field,{})
        if len(refs)!=len(SYMBOLS) or {Path(p).name for p in refs}!={s+suffix for s in SYMBOLS}:
            raise ValueError('Complete private history evidence required')
        for path,sha in refs.items():
            if evidence.file_digest(path)!=sha: raise ValueError('Changed historical input evidence')


def collect_packet(directory,prior,actions,calendar,history_evidence,session,get,clock=now):
    from causal_shadow_bundle import infer
    from split_context_audit import events_from_pages
    from active_stock_research import SYMBOLS
    manifest,protocol=validate(directory)
    opening,available,deadline=timing(session)
    moment=clock();local=moment.astimezone(ZoneInfo('America/New_York'))
    if str(local.date())!=session or local.weekday()>=5 or session<manifest['forward_start'] or not available<=moment<deadline:
        raise ValueError('Outside current prospective capture window; no backfill')
    verify_history_receipt(history_evidence,session,moment)
    calendar_session(calendar,session)
    if not actions or actions[-1].get('next_page_token') is not None: raise ValueError('Incomplete corporate actions')
    events=events_from_pages(actions,SYMBOLS)
    if any(e['ex_date']>session for e in events): raise ValueError('Future split in current receipt')
    if set(prior)!=set(SYMBOLS) or any(d>=session for days in prior.values() for d in days): raise ValueError('Prior-only fixed-universe history required')
    raw=get('https://data.alpaca.markets/v2/stocks/bars',dict(symbols=','.join(SYMBOLS),timeframe='1Min',
        feed='sip',adjustment='raw',limit=10000,start=opening.astimezone(timezone.utc).isoformat(),
        end=(opening+timedelta(minutes=30,microseconds=-1)).astimezone(timezone.utc).isoformat()))
    received=clock()
    if not available<=received<deadline: raise ValueError('Opening data arrived too late')
    current=opening_observations(raw,session)
    combined={s:dict(prior[s],**{session:current[s]}) for s in SYMBOLS}
    forecast=infer(directory,combined,events,session)
    snapshots=dict(opening=raw,calendar=calendar,corporate_actions=actions,history_provenance=history_evidence,inference=forecast)
    receipts={}
    for name,value in snapshots.items():
        target=directory/'receipts'/f'{session}_{name}.json'
        evidence.write_once(target,value);receipts[name]=dict(path=str(target),sha256=evidence.file_digest(target))
    captured=clock()
    if not available<=received<=captured<deadline: raise ValueError('Inference/receipt retention missed entry deadline')
    if evidence.timestamp(protocol['protocol']['created_utc'])>=opening or evidence.timestamp(manifest['created_utc'])>=opening:
        raise ValueError('Model/collector was not fixed before cutoff')
    record=dict(schema=1,session_date=session,captured_utc=captured.isoformat(),received_utc=received.isoformat(),
        hypothetical_entry_not_before_utc=deadline.astimezone(timezone.utc).isoformat(),
        manifest_sha256=evidence.read_manifest(directory)['manifest_sha256'],collector_protocol_sha256=protocol['protocol_sha256'],
        source_workflow_sha=os.environ.get('GITHUB_SHA'),workflow_run_id=os.environ.get('GITHUB_RUN_ID'),
        predictions=[dict(symbol=p['symbol'],probabilities=p['probabilities']) for p in forecast['predictions']],
        receipts=receipts,orders=False,production_approved=False,external_timestamp_anchor_verified=False,
        independent_validation_pass=False,raw_data_published=False)
    packet=dict(record=record,record_sha256=evidence.digest(record))
    evidence.write_once(directory/'predictions'/f'{session}.json',packet)
    return packet


def split_pages(get,session,start):
    from active_stock_research import SYMBOLS
    from split_context_audit import URL
    params=dict(symbols=','.join(SYMBOLS),types='forward_split,reverse_split',start=start,end=session,limit=1000,sort='asc')
    pages=[];seen=set()
    for _ in range(10):
        page=get(URL,params);pages.append(page);token=page.get('next_page_token')
        if token is None: return pages
        if not isinstance(token,str) or not token or token in seen: raise ValueError('Ambiguous split pagination')
        seen.add(token);params=dict(params,page_token=token)
    raise ValueError('Split pagination cap reached')


def cloud_collect(directory):
    from active_stock_research import SYMBOLS,fetch_symbol
    from causal_opening_inventory import load_observations
    from prospective_model_collector import get_json
    manifest,_=validate(directory)
    if not preparation_window(now(),manifest['forward_start']): return status('skipped_outside_preparation_window')
    local=now().astimezone(ZoneInfo('America/New_York'));session=str(local.date())
    calendar=get_json('https://paper-api.alpaca.markets/v2/calendar',dict(start=session,end=session))
    if calendar==[]: return status('skipped_exchange_closed')
    calendar_session(calendar,session)
    start=str(local.date()-timedelta(days=100));HISTORY.mkdir(parents=True,exist_ok=True)
    history_started=now()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda s:fetch_symbol(s,HISTORY,start,session),SYMBOLS))
    prior,quality=load_observations(HISTORY)
    if any(d>=session for days in prior.values() for d in days): raise ValueError('Downloaded history crossed current session')
    actions=split_pages(get_json,session,start)
    history_evidence=dict(start=start,end_exclusive=session,feed='sip',adjustment='raw',
        download_started_utc=history_started.isoformat(),prepared_utc=now().isoformat(),observations=quality,
        history_files={str(HISTORY/f'{s}.csv'):evidence.file_digest(HISTORY/f'{s}.csv') for s in SYMBOLS},
        metadata_files={str(HISTORY/f'{s}.metadata.json'):evidence.file_digest(HISTORY/f'{s}.metadata.json') for s in SYMBOLS},
        original_historical_delivery_authenticated=False)
    available=timing(session)[1]
    while now()<available: timer.sleep(min(30,max(.01,(available-now()).total_seconds())))
    packet=collect_packet(directory,prior,actions,calendar,history_evidence,session,get_json)
    return status('local_forecast_external_anchor_pending',recorded_sessions=1,record_sha256=packet['record_sha256'])


def status(value,**fields):
    if set(fields)-{'recorded_sessions','record_sha256','error_type'}: raise ValueError('Unsupported status field')
    result=dict(status=value,updated_utc=now().isoformat(),recorded_sessions=0,orders=False,
        production_approved=False,independent_validation_pass=False)
    result.update(fields)
    STATUS.parent.mkdir(parents=True,exist_ok=True);STATUS.write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps(result),flush=True);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['register','plan','validate','collect','seal']);p.add_argument('--directory',type=Path,default=ROOT)
    args=p.parse_args()
    try:
        if args.mode=='register': register(args.directory)
        elif args.mode=='plan':
            m=evidence.read_manifest(args.directory)['manifest'];run=preparation_window(now(),m['forward_start'])
            if os.environ.get('GITHUB_OUTPUT'):
                with open(os.environ['GITHUB_OUTPUT'],'a') as handle: handle.write(f'run={str(run).lower()}\n')
            print(json.dumps(dict(run=run,orders=False)))
        elif args.mode=='validate':
            validate(args.directory);status('shadow_environment_validated_only')
        elif args.mode=='seal':
            from research_evidence_crypto import seal
            seal(args.directory,HISTORY)
        else: cloud_collect(args.directory)
    except Exception as error:
        status('failed_no_forecast_claim',error_type=type(error).__name__)
        raise RuntimeError('Classified shadow research failure; no orders issued') from None
