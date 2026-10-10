"""Discover all frozen-control runs, then evaluate cumulative evidence. GET only."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path

from dotenv import load_dotenv
from prospective_forecast_evidence import read_manifest,timestamp,source_matches,file_digest
from prospective_outcome_audit import get,headers
from prospective_series_audit import audit_series
from research_evidence_crypto import evidence_key

WORKFLOW='predictive-prospective.yml'


def discover(envelope,request=get,auth=None):
    """Include failed terminal runs; never filter for profitable forecasts."""
    auth=headers() if auth is None else auth
    cutoff=timestamp(envelope['manifest']['created_utc'])
    seen=set();terminal=[];pending=[];records=[]
    for page in range(1,101):
        data=request(f'/actions/workflows/{WORKFLOW}/runs',auth,
            {'per_page':100,'page':page}).json()
        items=data['workflow_runs']
        for run in items:
            if run['id'] in seen: raise ValueError('Duplicate workflow run in discovery')
            seen.add(run['id'])
            if run.get('path')!='.github/workflows/'+WORKFLOW:
                raise ValueError('Unexpected workflow path')
            if timestamp(run['created_at'])<cutoff: continue
            records.append({k:run.get(k) for k in
                ['id','created_at','status','conclusion','event','head_sha']})
            (terminal if run['status']=='completed' else pending).append(run['id'])
        if len(items)<100: break
    else: raise ValueError('Incomplete workflow-run pagination')
    return dict(terminal_run_ids=sorted(terminal),pending_run_ids=sorted(pending),
        runs=sorted(records,key=lambda r:r['id']),orders=False,
        note='Run discovery is not proof of timely forecasts or successful execution')


def run(model_dir,backup,output,validate_only=False):
    envelope=read_manifest(model_dir)
    if not source_matches(envelope['manifest']): raise ValueError('Frozen source mismatch')
    if file_digest(model_dir/'model.joblib')!=envelope['manifest']['artifact_sha256']:
        raise ValueError('Frozen model mismatch')
    evidence_key()  # Fail before an audit if the independent key is unavailable.
    output.mkdir(parents=True,exist_ok=True)
    report=dict(status='environment_validation_only',orders=False,
        independent_validation_pass=False,production_approved=False,
        verified_forecast_sessions=0,retrieved_utc=datetime.now(timezone.utc).isoformat())
    if not validate_only:
        discovery=discover(envelope)
        (output/'discovery.json').write_text(json.dumps(discovery,indent=2,allow_nan=False))
        report=audit_series(discovery['terminal_run_ids'],backup,model_dir,output/'results.json')
        report['pending_run_ids']=discovery['pending_run_ids']
        # A pending run is not treated as a no-trade day or proven success.
        report['discovery_complete']=not discovery['pending_run_ids']
        report['performance_screen_pass'] &= report['discovery_complete']
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({k:report.get(k) for k in
        ['status','provenance_verified_sessions','missing_completed_sessions',
         'performance_screen_pass','independent_validation_pass','orders']}))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--validate-only',action='store_true')
    p.add_argument('--model-dir',type=Path,default=Path('research_prospective/control_v2'))
    p.add_argument('--backup',type=Path,default=Path('research_runs/prospective_backups'))
    p.add_argument('--output',type=Path,default=Path('research_runs/prospective_automatic_audit'))
    a=p.parse_args();load_dotenv();run(a.model_dir,a.backup,a.output,a.validate_only)
