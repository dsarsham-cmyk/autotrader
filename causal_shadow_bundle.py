"""Own frozen causal/split shadow heads; no collector, scheduler or orders.

Pure inference does not create authenticated prospective evidence. A future
collector must retain raw receipts, anchor predictions before entry, and audit
outcomes separately. Existing control_v2 is never replaced or modified.
"""
import argparse
from datetime import date
import importlib.metadata
import json
from pathlib import Path
from zoneinfo import ZoneInfo
import warnings
import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
from active_stock_research import SYMBOLS
from balanced_target_simulator import path
from causal_opening_inventory import FEATURES,load_observations
from causal_sparse_research import market_maps
from predictive_portfolio_research import partition
from predictive_research import raw_score
import prospective_forecast_evidence as evidence
from split_context_audit import events_from_pages,iso_date,normalized_opening_rows
from split_predictive_research import flatten

TARGETS=(.004,.01)
RUNTIME=('numpy','pandas','scipy','scikit-learn','joblib','threadpoolctl')


def runtime_versions():
    return {n:importlib.metadata.version(n) for n in RUNTIME}


def fit_head(train,calibration,labels):
    if not train or not calibration or max(r['date'] for r in train)>=min(r['date'] for r in calibration):
        raise ValueError('Distinct past training/calibration date groups required')
    x=np.asarray([r['features'] for r in train]);cx=np.asarray([r['features'] for r in calibration])
    if x.shape[1:]!=(len(FEATURES),) or cx.shape[1:]!=(len(FEATURES),) or not np.isfinite(x).all() or not np.isfinite(cx).all():
        raise ValueError('Finite16-feature input schema required')
    model=make_pipeline(StandardScaler(),LogisticRegression(C=.1,max_iter=1000,random_state=19))
    calibrator=LogisticRegression(C=1,max_iter=1000,random_state=19)
    with warnings.catch_warnings(record=True) as observed:
        warnings.simplefilter('always')
        model.fit(x,[labels[(r['date'],r['symbol'])] for r in train])
        calibrator.fit(raw_score(model,cx),[labels[(r['date'],r['symbol'])] for r in calibration])
    if observed: raise ValueError('Unresolved fitted shadow-head warning')
    return dict(model=model,calibrator=calibrator)


def predict_head(head,rows):
    if not rows: return []
    x=np.asarray([r['features'] for r in rows])
    if x.shape[1:]!=(len(FEATURES),) or not np.isfinite(x).all(): raise ValueError('Invalid inference features')
    p=head['calibrator'].predict_proba(raw_score(head['model'],x))[:,1]
    if not np.isfinite(p).all() or (p<0).any() or (p>1).any(): raise ValueError('Invalid probabilities')
    return [float(v) for v in p]


def opening_inputs(observations,events,session):
    iso_date(session)
    if set(observations)!=set(SYMBOLS): raise ValueError('Fixed universe receipt required')
    if any(d>session for days in observations.values() for d in days): raise ValueError('Future history is forbidden')
    for days in observations.values():
        if session not in days or days[session].minute.tolist()!=list(range(570,600)):
            raise ValueError('Exactly30 current opening bars required; later/incomplete bars forbidden')
        values=days[session][['open','high','low','close','volume']].to_numpy(dtype=float)
        if (not np.isfinite(values).all() or (values[:,:4]<=0).any() or (values[:,4]<0).any() or
            (values[:,1]<values[:,[0,2,3]].max(axis=1)).any() or (values[:,2]>values[:,[0,3]].min(axis=1)).any()):
            raise ValueError('Invalid current opening OHLCV')
        prior_terminal=[d for d,r in days.items() if d<session and (r.minute>=955).any()]
        if not prior_terminal or (date.fromisoformat(session)-date.fromisoformat(max(prior_terminal))).days>4:
            raise ValueError('Prior terminal history stale; refresh before prospective inference')
    by_date,reasons,applications=normalized_opening_rows(observations,events)
    rows=[r for r in flatten(by_date) if r['date']==session]
    return rows,dict(candidate_symbols=[r['symbol'] for r in rows],
        eligibility={s:reasons[(session,s)] for s in SYMBOLS},
        split_applications=[a for a in applications if a['applied_before_session']==session])


def load_own_bundle(directory):
    manifest=evidence.read_manifest(directory)['manifest']
    target=directory/'model.joblib'
    if evidence.file_digest(target)!=manifest['artifact_sha256'] or not evidence.source_matches(manifest):
        raise ValueError('Changed own frozen shadow bundle; not deserialized')
    bundle=joblib.load(target)
    if (bundle.get('mode')!='causal_split_shadow_only' or bundle.get('orders') is not False or
        bundle.get('production_approved') is not False or bundle.get('features')!=FEATURES or
        bundle.get('symbols')!=list(SYMBOLS) or bundle.get('runtime_versions')!=runtime_versions()):
        raise ValueError('Incompatible research-only shadow bundle')
    return bundle,manifest


def infer(directory,observations,events,session):
    bundle,manifest=load_own_bundle(directory)
    if iso_date(session)<manifest['forward_start'] or session<=bundle['trained_through']:
        raise ValueError('No prospective backfill or overlap with training')
    rows,quality=opening_inputs(observations,events,session)
    predictions={name:predict_head(head,rows) for name,head in bundle['heads'].items()}
    return dict(session=session,predictions=[dict(symbol=r['symbol'],signal_price=r['signal_price'],
        probabilities={name:values[i] for name,values in predictions.items()}) for i,r in enumerate(rows)],
        input_quality=quality,orders=False,production_approved=False,
        authenticated_prospective_evidence=False,external_timestamp_anchor_verified=False)


def freeze_bundle(data,directory,reference,input_audit,forward_start,training_end='2026-10-01'):
    if directory.exists(): raise ValueError('Own experiment directory cannot be overwritten')
    iso_date(training_end);iso_date(forward_start)
    # Check date boundary before expensive fitting or creating output files.
    if training_end>=forward_start or forward_start<=str(evidence.utc_now().astimezone(ZoneInfo('America/New_York')).date()):
        raise ValueError('Strictly future start and strictly earlier training required')
    original=json.loads(reference.read_bytes())
    if original['status']!='completed_exposed_balanced_target_comparison': raise ValueError('Completed own-label study required')
    for name,expected in original['dependency_sha256'].items():
        if evidence.source_digest(name)!=expected: raise ValueError('Reference source changed')
    if evidence.file_digest(input_audit)!=original['input_audit_sha256']: raise ValueError('Input audit changed')
    receipt=input_audit.parent/'corporate_actions_receipt.json'
    if evidence.file_digest(receipt)!=original['corporate_action_receipt_sha256']: raise ValueError('Split receipt changed')
    observations,quality=load_observations(data)
    if quality!=original['evidence']: raise ValueError('Historical input bytes changed')
    observations={s:{d:r for d,r in days.items() if d<=training_end} for s,days in observations.items()}
    events=events_from_pages(json.loads(receipt.read_bytes())['pages'],list(SYMBOLS))
    by_date,_,_=normalized_opening_rows(observations,events);rows=flatten(by_date)
    dates=sorted({r['date'] for r in rows});market=market_maps(observations)
    if len(dates)<240 or dates[-1]!=training_end: raise ValueError('Complete requested training span required')
    heads={};counts={}
    with threadpool_limits(limits=1):
        for target in TARGETS:
            outcomes={(r['date'],r['symbol']):path(market.get(r['date'],{}).get(r['symbol'],{}),
                r['signal_price'],target_fraction=target) for r in rows}
            labels={k:o['label'] for k,o in outcomes.items() if o is not None and o['filled']}
            train,cal=[partition(rows,d) for d in (dates[:-60],dates[-60:])]
            train=[r for r in train if (r['date'],r['symbol']) in labels]
            cal=[r for r in cal if (r['date'],r['symbol']) in labels]
            name='target_004' if target==.004 else 'target_010'
            heads[name]=fit_head(train,cal,labels)
            counts[name]=dict(training_rows=len(train),calibration_rows=len(cal),target_fraction=target,
                train_last_observed=max(r['date'] for r in train),cal_last_observed=max(r['date'] for r in cal))
    bundle=dict(mode='causal_split_shadow_only',orders=False,production_approved=False,
        trained_through=training_end,features=FEATURES,symbols=list(SYMBOLS),feed='sip',adjustment='raw',
        runtime_versions=runtime_versions(),heads=heads,training_last=dates[-61],
        calibration_first=dates[-60],calibration_last=dates[-1],counts=counts,
        reference_sha256=evidence.file_digest(reference),input_evidence=quality,
        rule=dict(probability_threshold=.65,cutoff_minute=30,information_delay_minutes=15,
            execution_latency_minutes=1,horizon_minutes=60,stop_fraction=.01,
            targets=list(TARGETS),cost_bps=10,stress_cost_bps=20,stock_cap=.01,category_cap=.05,
            max_positions=3,planned_trade_risk=.0005),prior_exploration_failed_target=True)
    directory.mkdir(parents=True)
    joblib.dump(bundle,directory/'model.joblib')
    sources=list(original['dependency_sha256'])+['causal_shadow_bundle.py','prospective_forecast_evidence.py']
    envelope=evidence.freeze(directory,directory/'model.joblib',list(dict.fromkeys(sources)),
        training_end,forward_start,source_root=Path.cwd(),history_provenance_required=True)
    description=dict({k:v for k,v in bundle.items() if k!='heads'},forward_start=forward_start,
        collector_implemented=False,cloud_scheduled=False,forward_records=0,
        limitations=['Frozen fitted comparator, not independent forecast evidence',
            'No approved profitable model; exposed studies failed target',
            'Pure inference cannot replace actual input receipt and pre-entry external timestamp anchor'])
    evidence.write_once(directory/'description.json',description)
    print(json.dumps(dict(status='frozen_shadow_comparators_only',manifest_sha256=envelope['manifest_sha256'],
        artifact_sha256=envelope['manifest']['artifact_sha256'],counts=counts,
        collector_implemented=False,forward_records=0,orders=False)),flush=True)
    return bundle,envelope


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--directory',type=Path,default=Path('research_prospective/causal_split_shadow_v1'))
    p.add_argument('--reference',type=Path,default=Path('research_runs/balanced_target/results.json'))
    p.add_argument('--input-audit',type=Path,default=Path('research_runs/split_context_audit/results.json'))
    p.add_argument('--forward-start',default='2026-10-12');a=p.parse_args()
    freeze_bundle(a.data,a.directory,a.reference,a.input_audit,a.forward_start)
