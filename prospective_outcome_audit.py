"""Read-only artifact backup, anchor checks and future simulated-outcome audit.

Synthetic tests are not prospective observations. Simulated fills are not broker
execution. No trading permission is granted by any metric in this module.
"""
import argparse
from datetime import datetime,time,timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile
from zoneinfo import ZoneInfo

import numpy as np
import requests

from prospective_forecast_evidence import digest,timestamp,read_manifest
from predictive_portfolio_research import portfolio
from fixed_trade_cost_diagnostic import diagnostic

REPOSITORY='dsarsham-cmyk/autotrader'
BASE=f'https://api.github.com/repos/{REPOSITORY}'


def verify_archive(metadata,content):
    actual='sha256:'+hashlib.sha256(content).hexdigest()
    if metadata.get('digest')!=actual:
        raise ValueError('GitHub artifact/archive digest mismatch')
    return actual


def anchor_check(packet,metadata,envelope):
    record=packet['record'];manifest=envelope['manifest']
    if digest(record)!=packet['record_sha256'] or record['manifest_sha256']!=envelope['manifest_sha256']:
        raise ValueError('Forecast/manifest integrity mismatch')
    if record.get('broker_orders_enabled') is not False or record.get('production_approved') is not False:
        raise ValueError('Not a research forecast')
    session=record['session_date']
    if session<manifest['forward_start'] or session<=manifest['trained_through']:
        raise ValueError('Not a prospective session')
    captured=timestamp(record['captured_utc'])
    created=timestamp(metadata['created_at'])
    # Artifact creation precedes finalization. Require the remotely recorded
    # successful upload-step completion; timestamps have second resolution,
    # so conservatively use its upper bound one second later.
    completed=metadata.get('verified_upload_completed_at')
    anchored=timestamp(completed)+timedelta(seconds=1) if completed else None
    entry=timestamp(record['hypothetical_entry_not_before_utc'])
    cutoff=datetime.combine(datetime.fromisoformat(session).date(),time(9,30),ZoneInfo('America/New_York'))+timedelta(minutes=manifest['feature_cutoff_minute'])
    available=cutoff+timedelta(minutes=manifest['information_delay_minutes'])
    expected_entry=available+timedelta(minutes=manifest['execution_latency_minutes'])
    receipt=record['input_receipt']
    if entry!=expected_entry or not available<=captured<entry or timestamp(manifest['created_utc'])>=cutoff:
        raise ValueError('Forecast/entry chronology does not match frozen protocol')
    if receipt['feed']!=manifest['feed'] or timestamp(receipt['feature_cutoff_utc'])!=cutoff or timestamp(receipt['last_bar_end_utc'])!=cutoff:
        raise ValueError('Wrong observation cutoff or feed')
    if not available<=timestamp(receipt['received_utc'])<=captured:
        raise ValueError('Invalid data-receipt chronology')
    return dict(artifact_id=metadata['id'],session_date=session,
        artifact_created_utc=metadata['created_at'],captured_utc=record['captured_utc'],
        artifact_upload_completed_utc=completed,
        conservative_anchor_upper_bound_utc=anchored.isoformat() if anchored else None,
        timely_external_anchor=bool(anchored and created<=anchored and captured<=anchored<entry),
        record_sha256=packet['record_sha256'],
        note='Timing check requires metadata/ZIP digest verified directly against GitHub API')


def evaluate_simulated_session(packet,metadata,envelope,raw_opening,completed_bars):
    anchor=anchor_check(packet,metadata,envelope)
    if not anchor['timely_external_anchor']:
        raise ValueError('Late external anchor: not counted as timely forward evidence')
    record=packet['record'];session=record['session_date']
    if raw_opening.get('next_page_token'): raise ValueError('Incomplete raw opening evidence')
    rows=[];stocks={};seen=set()
    for prediction in record['predictions']:
        symbol=prediction['symbol']
        if symbol in seen: raise ValueError('Duplicate forecast symbol')
        seen.add(symbol)
        p=prediction['probability']
        if not np.isfinite(p) or not 0<=p<=1: raise ValueError('Invalid forecast probability')
        a=np.asarray(completed_bars[symbol],dtype=float)
        if a.shape!=(390,5) or not np.isfinite(a).all():
            raise ValueError('Complete validated 390-minute SIP outcome data required')
        if (a[:,:4]<=0).any() or (a[:,4]<0).any() or (a[:,1]<a[:,[0,3]].max(axis=1)).any() or (a[:,2]>a[:,[0,3]].min(axis=1)).any():
            raise ValueError('Invalid outcome OHLCV prices')
        opening=sorted(raw_opening['bars'][symbol],key=lambda r:r['t'])
        if len(opening)!=30: raise ValueError('Opening feature packet must have 30 bars')
        opening_start=datetime.combine(datetime.fromisoformat(session).date(),time(9,30),ZoneInfo('America/New_York'))
        if [timestamp(r['t']) for r in opening]!=[opening_start+timedelta(minutes=i) for i in range(30)]:
            raise ValueError('Original opening timestamps do not match the session')
        prefix=np.array([[r[k] for k in ['o','h','l','c','v']] for r in opening])
        if not np.allclose(a[:30],prefix,rtol=0,atol=1e-8):
            raise ValueError('Outcome-data opening differs from original feature input')
        rows.append(dict(date=session,symbol=symbol,probability=p,signal_price=float(prefix[-1,3])))
        stocks[symbol]=(a,{})
    # This exact frozen control has .65 threshold, target .4%, stop 1%, a
    # minute-30 feature cutoff, 15-minute information delay and one-minute entry
    # latency. Not a sweep to choose favorable thresholds after observing data.
    manifest=envelope['manifest']
    if (manifest['feature_cutoff_minute'],manifest['information_delay_minutes'],
        manifest['execution_latency_minutes'])!=(30,15,1):
        raise ValueError('Unsupported timing; do not silently change frozen control')
    outcomes=[portfolio(rows,{session:stocks},30,'target_60',.65,cost,delay)
              for cost,delay in [(10,16),(20,16),(10,17)]]
    primary=outcomes[0]
    day=primary['daily'][0] if primary['daily'] else None
    budget_pass=day is None or day['committed_usd']<=100000*.05+1e-7
    trades=primary['trades']
    stock_pass=all(t['quantity']*t['raw_entry']*1.001<=100000*.01+1e-7 for t in trades)
    return dict(status='anchored_single_session_simulation_only',anchor=anchor,
        outcomes=outcomes,cost_diagnostic=diagnostic(primary),
        category_budget_pass=budget_pass,stock_budget_pass=stock_pass,
        max_positions_pass=len(trades)<=3,broker_orders_enabled=False,
        independent_validation_pass=False,production_approved=False,
        limitations=['One-session virtual capital resets to 100000: not cumulative account replay',
            'Metadata consistency does not replace API retrieval/digest verification',
            'Raw and history provenance plus actual market-bar timestamps still need end-to-end verification',
            'OHLC simulated fills/stops/costs are not broker execution',
            'Small experimental sleeve does not prove whole-account guard behavior'])


def headers():
    token=os.environ.get('GITHUB_TOKEN')
    if not token:
        response=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',
            capture_output=True,text=True,check=True)
        values=dict(line.split('=',1) for line in response.stdout.splitlines() if '=' in line)
        token=values['password']
    return {'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'}


def get(path,auth,params=None):
    response=requests.get(BASE+path,headers=auth,params=params,timeout=30)
    if response.status_code!=200: raise RuntimeError(f'GitHub read HTTP {response.status_code}')
    return response


def save_once_or_identical(path,content):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=content: raise ValueError('Existing evidence differs; not overwritten')
    else:
        with path.open('xb') as handle: handle.write(content)


def inspect_run(run_id,backup,envelope):
    auth=headers()
    run=get(f'/actions/runs/{run_id}',auth).json()
    if run.get('path')!='.github/workflows/predictive-prospective.yml' or run.get('status')!='completed':
        raise ValueError('Wrong workflow or run not terminal')
    artifacts=[]
    for page in range(1,101):
        result=get(f'/actions/runs/{run_id}/artifacts',auth,{'per_page':100,'page':page}).json()
        items=result['artifacts'];artifacts.extend(items)
        if len(items)<100: break
    else: raise ValueError('Incomplete artifact pagination')
    root=backup/str(run_id);anchors=[];statuses=[];retained=[]
    upload_steps=[]
    for page in range(1,101):
        result=get(f'/actions/runs/{run_id}/jobs',auth,{'filter':'all','per_page':100,'page':page}).json()
        jobs=result['jobs']
        upload_steps.extend(dict(job_id=job['id'],completed_at=step['completed_at'])
            for job in jobs for step in job.get('steps',[]) if step['name']=='Timestamp forecast and status externally'
            and step['conclusion']=='success' and step.get('completed_at'))
        if len(jobs)<100: break
    else: raise ValueError('Incomplete workflow-job pagination')
    for metadata in artifacts:
        if not metadata['name'].startswith(('prospective-forecast-','prospective-private-encrypted-')): continue
        if metadata.get('workflow_run',{}).get('id')!=run_id or metadata.get('expired'):
            raise ValueError('Artifact ownership mismatch or expired evidence')
        raw=get(f'/actions/artifacts/{metadata["id"]}/zip',auth).content
        verify_archive(metadata,raw)
        save_once_or_identical(root/f'{metadata["id"]}.zip',raw)
        metadata_path=root/f'{metadata["id"]}.metadata.json'
        if not metadata_path.exists():
            save_once_or_identical(metadata_path,json.dumps(metadata,indent=2).encode())
        retained.append(metadata['id'])
        if metadata['name'].startswith('prospective-forecast-'):
            matches=[s for s in upload_steps if timestamp(s['completed_at'])+timedelta(seconds=1)>=timestamp(metadata['created_at'])]
            if matches:
                step=min(matches,key=lambda s:timestamp(s['completed_at']))
                metadata=dict(metadata,verified_upload_completed_at=step['completed_at'],verified_upload_job_id=step['job_id'])
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for name in archive.namelist():
                    if name.endswith('/cloud_status.json') or name=='cloud_status.json':
                        statuses.append(json.loads(archive.read(name)))
                    elif '/predictions/' in name and name.endswith('.json'):
                        anchors.append(anchor_check(json.loads(archive.read(name)),metadata,envelope))
    report=dict(run_id=run_id,run_url=run['html_url'],conclusion=run['conclusion'],
        authenticated_archive_digests=True,retained_artifacts=retained,statuses=statuses,
        forecast_packets=len(anchors),timely_anchored_packets=sum(a['timely_external_anchor'] for a in anchors),
        anchors=anchors,independent_validation_pass=False,orders=False,
        note='Retained local backup; retrieval not itself a win, forecast or broker execution')
    (root/'inspection.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(report,indent=2));return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',type=int,required=True)
    parser.add_argument('--backup',type=Path,default=Path('research_runs/prospective_backups'))
    args=parser.parse_args()
    inspect_run(args.run_id,args.backup,read_manifest('research_prospective/control_v2'))
