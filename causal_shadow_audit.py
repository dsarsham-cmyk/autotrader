"""Discover/digest/decrypt/replay paired shadows and continuous virtual ledgers.

GET only. Missing/late/failed evidence is not a no-trade day; technical or
simulated performance screens never authorize live trading or model promotion.
"""
import argparse
from datetime import datetime,timedelta,time,timezone
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import zipfile
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from causal_shadow_collector import ROOT,validate,timing,calendar_session
from causal_shadow_replay import HEADS,anchor_check,reproduce,outcome_market
from balanced_target_simulator import portfolio
from prospective_forecast_evidence import digest,timestamp,source_digest,read_manifest
from prospective_full_audit import decrypt_private_archive
from prospective_outcome_audit import get,headers,verify_archive,save_once_or_identical
from prospective_model_collector import get_json
from prospective_series_audit import accounting_metrics
from finbert_comparison_audit import check
from research_evidence_crypto import evidence_key

WORKFLOW='causal-shadow-prospective.yml'
UPLOAD_STEP='Timestamp shadow predictions and status externally'
VARIANTS=((10,16),(20,16),(10,17))


def pages(path,key,auth,request=get,extra=None):
    items=[];seen=set();total=None
    for page in range(1,101):
        data=request(path,auth,dict(extra or {},per_page=100,page=page)).json()
        batch=data[key]
        if not isinstance(batch,list): raise ValueError('Invalid paginated response')
        reported=data.get('total_count')
        if total is None: total=reported
        if reported!=total: raise ValueError('Pagination changed during observation')
        for item in batch:
            if item['id'] in seen: raise ValueError('Duplicate paginated identity')
            seen.add(item['id']);items.append(item)
        if len(batch)<100:
            if total is not None and len(items)!=total: raise ValueError('Incomplete paginated observation')
            return items
    raise ValueError('Pagination cap reached')


def discover(directory,auth,request=get):
    _,p=validate(directory);cutoff=timestamp(p['protocol']['created_utc'])
    rows=pages('/actions/workflows/'+WORKFLOW+'/runs','workflow_runs',auth,request)
    if any(r.get('path')!='.github/workflows/'+WORKFLOW for r in rows): raise ValueError('Wrong discovered workflow')
    rows=[r for r in rows if timestamp(r['created_at'])>=cutoff]
    return dict(runs=[{k:r.get(k) for k in ['id','created_at','status','conclusion','event','head_sha','run_attempt']} for r in rows],
        terminal_run_ids=sorted(r['id'] for r in rows if r['status']=='completed'),
        pending_run_ids=sorted(r['id'] for r in rows if r['status']!='completed'),orders=False)


def inspect_run(run_id,directory,backup,auth,request=get):
    run=request(f'/actions/runs/{run_id}',auth).json()
    if run.get('path')!='.github/workflows/'+WORKFLOW or run.get('status')!='completed' or run.get('run_attempt')!=1:
        raise ValueError('Unsupported workflow/run attempt')
    artifacts=pages(f'/actions/runs/{run_id}/artifacts','artifacts',auth,request)
    jobs=pages(f'/actions/runs/{run_id}/jobs','jobs',auth,request,{'filter':'all'})
    steps=[s for j in jobs for s in j.get('steps',[]) if s['name']==UPLOAD_STEP and s.get('conclusion')=='success' and s.get('completed_at')]
    root=backup/str(run_id);packets=[];encrypted=[];statuses=[];retained=[]
    for meta in artifacts:
        prefix='causal-shadow-forecast-' if meta['name'].startswith('causal-shadow-forecast-') else 'causal-shadow-private-encrypted-'
        if meta['name']!=prefix+str(run_id): raise ValueError('Unexpected shadow artifact')
        if meta.get('workflow_run',{}).get('id')!=run_id or meta.get('expired'): raise ValueError('Expired or unowned artifact')
        response=request(f'/actions/artifacts/{meta["id"]}/zip',auth)
        verify_archive(meta,response.content)
        save_once_or_identical(root/f'{meta["id"]}.zip',response.content)
        metadata_path=root/f'{meta["id"]}.metadata.json'
        if not metadata_path.exists(): save_once_or_identical(metadata_path,json.dumps(meta,sort_keys=True).encode())
        retained.append(meta['id'])
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names=archive.namelist()
            if len(set(names))!=len(names) or sum(i.file_size for i in archive.infolist())>512*1024*1024:
                raise ValueError('Oversized or duplicate ZIP evidence')
            for name in names:
                path=PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts: raise ValueError('Unsafe ZIP member')
                if name.endswith('/'): continue
                if name.endswith('causal_shadow_cloud_status.json'):
                    statuses.append(json.loads(archive.read(name)))
                elif '/predictions/' in name and name.endswith('.json') and prefix=='causal-shadow-forecast-':
                    if len(steps)!=1: raise ValueError('Ambiguous upload-step completion')
                    bound=dict(meta,verified_upload_completed_at=steps[0]['completed_at'])
                    packet=json.loads(archive.read(name));anchor=anchor_check(packet,bound,run,directory)
                    packets.append((packet,anchor))
                elif name.endswith('private_evidence.aesgcm') and prefix=='causal-shadow-private-encrypted-':
                    encrypted.append(archive.read(name))
                else: raise ValueError('Unexpected evidence file')
    if any(s.get('orders') is not False or s.get('production_approved') is not False for s in statuses):
        raise ValueError('Unsafe cloud status')
    accepted=[];excluded=[]
    timely=[(p,a) for p,a in packets if a['timely_external_anchor']]
    for p,a in packets:
        if not a['timely_external_anchor']: excluded.append(dict(session_date=a['session_date'],status='late_or_missing_external_anchor'))
    if timely:
        if len(encrypted)!=1: raise ValueError('One dedicated encrypted archive required')
        files=decrypt_private_archive(encrypted[0])
        for packet,anchor in timely:
            verified=reproduce(packet,files,directory,root)
            verified.update(anchor=anchor,run_id=run_id);accepted.append(verified)
    inspection=dict(run_id=run_id,run_conclusion=run['conclusion'],statuses=statuses,retained_artifacts=retained,
        forecast_packets=len(packets),timely_anchor_packets=len(timely),reproduced_packets=len(accepted),excluded=excluded,
        orders=False,independent_validation_pass=False)
    (root/'inspection.json').write_text(json.dumps(inspection,indent=2,allow_nan=False))
    return inspection,accepted


def completed_calendar(directory,work,moment=None,provider=get_json):
    moment=moment or datetime.now(timezone.utc)
    if moment.tzinfo is None: raise ValueError('Aware completed-session clock required')
    manifest,_=validate(directory);first=manifest['forward_start'];last=str(moment.astimezone(ZoneInfo('America/New_York')).date())
    raw=[] if first>last else provider('https://paper-api.alpaca.markets/v2/calendar',dict(start=first,end=last))
    if not isinstance(raw,list): raise ValueError('Invalid calendar response')
    completed=[];seen=set()
    for row in raw:
        session=row['date']
        if session in seen or not first<=session<=last: raise ValueError('Duplicate/out-of-range exchange session')
        seen.add(session);calendar_session([row],session)
        close=datetime.combine(datetime.fromisoformat(session).date(),time.fromisoformat(row['close']),ZoneInfo('America/New_York'))
        if close+timedelta(minutes=16)<=moment: completed.append(row)
    encoded=json.dumps(dict(observed_utc=moment.isoformat(),calendar=raw),sort_keys=True,separators=(',',':')).encode()
    sha=hashlib.sha256(encoded).hexdigest();save_once_or_identical(work/'calendar'/f'{sha}.json',encoded)
    return sorted(completed,key=lambda r:r['date']),sha


def completed_outcome(session,work,provider=get_json):
    from active_stock_research import SYMBOLS
    opening,_,_=timing(session)
    params=dict(symbols=','.join(SYMBOLS),timeframe='1Min',feed='sip',adjustment='raw',limit=10000,
        start=opening.astimezone(timezone.utc).isoformat(),end=(opening+timedelta(minutes=108,microseconds=-1)).astimezone(timezone.utc).isoformat())
    pages=[];seen=set();merged={}
    for _ in range(10):
        raw=provider('https://data.alpaca.markets/v2/stocks/bars',params);pages.append(raw)
        for s,rows in raw.get('bars',{}).items(): merged.setdefault(s,[]).extend(rows)
        token=raw.get('next_page_token')
        if token is None: break
        if not isinstance(token,str) or not token or token in seen: raise ValueError('Ambiguous outcome pagination')
        seen.add(token);params=dict(params,page_token=token)
    else: raise ValueError('Outcome pagination cap reached')
    packet=dict(session=session,feed='sip',adjustment='raw',observed_utc=datetime.now(timezone.utc).isoformat(),pages=pages)
    encoded=json.dumps(packet,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    sha=hashlib.sha256(encoded).hexdigest();save_once_or_identical(work/'outcomes'/f'{session}_{sha}.json',encoded)
    return dict(bars=merged,next_page_token=None),sha


def evaluate_series(completed,accepted,pending=False,errors=False):
    dates=[r['date'] for r in completed]
    if dates!=sorted(set(dates)): raise ValueError('Unique chronological exchange dates required')
    groups={}
    for v in accepted: groups.setdefault(v['session'],[]).append(v)
    duplicates=sorted(d for d,v in groups.items() if len(v)!=1)
    missing=[d for d in dates if d not in groups or len(groups[d])!=1]
    prefix=[]
    for d in dates:
        if d in missing: break
        prefix.append(groups[d][0])
    market={v['session']:v['market'] for v in prefix};cases=[]
    for head,target in HEADS.items():
        rows=[];no_eligible=[]
        for v in prefix:
            if not v['predictions']:
                # Computational calendar row, NOT an invented model forecast/win.
                no_eligible.append(v['session'])
                rows.append(dict(date=v['session'],symbol='__NO_ELIGIBLE__',signal_price=1.,probability=0.))
            for p in v['predictions']:
                rows.append(dict(date=v['session'],symbol=p['symbol'],signal_price=p['signal_price'],probability=p['probabilities'][head]))
        outcomes=[]
        for cost,delay in VARIANTS:
            result=portfolio(rows,market,.65,cost,delay,target)
            metrics=accounting_metrics(dict(result,profit_usd=result['known_prefix_profit_usd']),rows)
            full=bool(dates and not missing and not pending and not errors and result['full_period_coverage_complete'])
            result.update(expected_forecast_sessions=len(dates),known_prefix_metrics=metrics,
                full_period_coverage_complete=full,valid_no_eligible_sessions=no_eligible,
                target_screen_pass=bool(full and result['target_screen_pass']),independent_validation_pass=False)
            if not full:
                result.update(status='incomplete_or_empty_forward_evidence',profit_usd=None,
                    active_day_win_rate_pct=None,win_rate_interval=None)
            risk_pass=check(result)
            result['performance_screen_pass']=bool(result['target_screen_pass'] and risk_pass)
            outcomes.append(result)
        cases.append(dict(model=head,target_fraction=target,outcomes=outcomes))
    return dict(completed_sessions=dates,missing_completed_sessions=missing,duplicate_forecast_sessions=duplicates,
        outcome_ready_forecast_sessions=sum(len(groups.get(d,[]))==1 for d in dates),
        known_continuous_input_prefix_sessions=len(prefix),unreplayed_later_verified_sessions=[d for d in dates if d not in missing and d not in {v['session'] for v in prefix}],
        cases=cases,performance_screen_pass=any(c['outcomes'][0]['performance_screen_pass'] for c in cases),
        independent_validation_pass=False,production_approved=False,orders=False)


def run(directory,backup,output,validate_only=False):
    validate(directory);evidence_key();output.mkdir(parents=True,exist_ok=True)
    if validate_only:
        report=dict(status='shadow_audit_environment_validation_only',verified_forecast_sessions=0,
            performance_screen_pass=False,independent_validation_pass=False,orders=False)
    else:
        auth=headers();discovery=discover(directory,auth);accepted=[];inspections=[];failures=[];provenance=[]
        completed,calendar_sha=completed_calendar(directory,backup)
        completed_dates={r['date'] for r in completed}
        for run_id in discovery['terminal_run_ids']:
            try:
                inspected,rows=inspect_run(run_id,directory,backup,auth);inspections.append(inspected)
                for v in rows:
                    if v['session'] not in completed_dates: continue
                    provenance.append(dict(session=v['session'],run_id=v['run_id'],record_sha256=v['record_sha256']))
                    raw,sha=completed_outcome(v['session'],backup)
                    v.update(market=outcome_market(v['raw_opening'],raw,v['session']),outcome_sha256=sha)
                    accepted.append(v)
            except Exception as error:
                failures.append(dict(run_id=run_id,status='evidence_unavailable_not_a_no_trade_day',error_type=type(error).__name__))
        report=evaluate_series(completed,accepted,bool(discovery['pending_run_ids']),bool(failures))
        report.update(status='paired_shadow_forward_evidence_audit',discovery=discovery,inspections=inspections,
            verified_forecast_sessions=len({v['session'] for v in provenance}),provenance_records=provenance,
            failures=failures,calendar_sha256=calendar_sha,
            verified_records=[dict(session=v['session'],run_id=v['run_id'],record_sha256=v['record_sha256'],
                outcome_sha256=v['outcome_sha256'],anchor=v['anchor']) for v in accepted],
            limitations=['OHLC/cost/delay simulation is not broker execution or real-fill protection',
                'Correlated financial days, multiple comparator selection and modeled execution prevent automatic approval',
                'Artifacts expire; durable encrypted backup approval/implementation is still pending'])
    report['audited_utc']=datetime.now(timezone.utc).isoformat()
    report['parent_manifest_sha256']=read_manifest(directory)['manifest_sha256']
    report['audit_source_sha256']={s:source_digest(s) for s in ['causal_shadow_audit.py','causal_shadow_replay.py',
        'prospective_full_audit.py','prospective_outcome_audit.py','finbert_comparison_audit.py','prospective_series_audit.py']}
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({k:report.get(k) for k in ['status','verified_forecast_sessions','missing_completed_sessions','performance_screen_pass','independent_validation_pass','orders']}),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=ROOT)
    p.add_argument('--backup',type=Path,default=Path('research_runs/causal_shadow_backups'))
    p.add_argument('--output',type=Path,default=Path('research_runs/causal_shadow_audit'));p.add_argument('--validate-only',action='store_true')
    a=p.parse_args();load_dotenv();run(a.directory,a.backup,a.output,validate_only=a.validate_only)
