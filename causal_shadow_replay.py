"""Verify paired-shadow timing and reproduce retained inputs. No orders.

An externally anchored forecast is not proof of real fills, profitability,
independent financial days or permission to promote a model.
"""
from datetime import timedelta
import json
import math
from pathlib import Path,PurePosixPath
import numpy as np
from active_stock_research import SYMBOLS
from causal_opening_inventory import load_observations
from causal_shadow_bundle import infer
from causal_shadow_collector import validate,timing,opening_observations,calendar_session
from prospective_forecast_evidence import digest,timestamp,file_digest
from prospective_full_audit import retained_file
from prospective_outcome_audit import save_once_or_identical
from split_context_audit import events_from_pages

HEADS={'target_004':.004,'target_010':.01}


def anchor_check(packet,metadata,run,directory):
    manifest,protocol=validate(directory)
    from prospective_forecast_evidence import read_manifest
    record=packet['record'];session=record['session_date']
    if (digest(record)!=packet['record_sha256'] or record.get('schema')!=1 or
        record.get('manifest_sha256')!=read_manifest(directory)['manifest_sha256'] or
        record.get('collector_protocol_sha256')!=protocol['protocol_sha256']):
        raise ValueError('Shadow forecast/recipe integrity mismatch')
    if record.get('orders') is not False or record.get('production_approved') is not False:
        raise ValueError('Not a research-only forecast')
    if (run.get('path')!='.github/workflows/causal-shadow-prospective.yml' or run.get('status')!='completed' or
        run.get('run_attempt')!=1 or run.get('head_branch')!='main' or
        str(run['id'])!=record.get('workflow_run_id') or run['head_sha']!=record.get('source_workflow_sha') or
        metadata.get('workflow_run',{}).get('id')!=run['id'] or
        metadata.get('workflow_run',{}).get('head_sha')!=run['head_sha']):
        raise ValueError('Unsupported run/attempt or artifact ownership')
    opening,available,entry=timing(session)
    captured=timestamp(record['captured_utc']);received=timestamp(record['received_utc'])
    if (session<manifest['forward_start'] or session<=manifest['trained_through'] or opening.weekday()>=5 or
        timestamp(record['hypothetical_entry_not_before_utc'])!=entry or
        not available<=received<=captured<entry or timestamp(manifest['created_utc'])>=opening or
        timestamp(protocol['protocol']['created_utc'])>=opening):
        raise ValueError('Forecast/recipe chronology mismatch')
    completed=metadata.get('verified_upload_completed_at')
    bound=timestamp(completed)+timedelta(seconds=1) if completed else None
    timely=bool(bound and timestamp(metadata['created_at'])<=bound and captured<=bound<entry)
    return dict(session_date=session,record_sha256=packet['record_sha256'],
        artifact_id=metadata['id'],upload_completed_at=completed,
        conservative_anchor_upper_bound=bound.isoformat() if bound else None,
        timely_external_anchor=timely,orders=False,independent_validation_pass=False)


def compare_predictions(expected,published):
    if len({r['symbol'] for r in published})!=len(published): raise ValueError('Duplicate published symbol')
    if [r['symbol'] for r in expected]!=[r['symbol'] for r in published]: raise ValueError('Forecast candidate order/set mismatch')
    for a,b in zip(expected,published):
        if set(b)!= {'symbol','probabilities'} or set(b['probabilities'])!=set(HEADS): raise ValueError('Unknown prediction schema')
        for head in HEADS:
            p=b['probabilities'][head]
            if isinstance(p,bool) or not isinstance(p,(int,float)) or not math.isfinite(p) or not 0<=p<=1:
                raise ValueError('Invalid published probability')
            if not np.isclose(a['probabilities'][head],p,rtol=0,atol=1e-8): raise ValueError('Published probability not reproduced')


def reproduce(packet,files,directory,work):
    record=packet['record'];session=record['session_date'];refs=record['receipts']
    if set(refs)!={'opening','calendar','corporate_actions','history_provenance','inference'}:
        raise ValueError('Complete retained input chain required')
    snapshots={name:json.loads(retained_file(files,r['path'],r['sha256'])) for name,r in refs.items()}
    calendar_session(snapshots['calendar'],session)
    history=snapshots['history_provenance']
    if history.get('feed')!='sip' or history.get('adjustment')!='raw' or history.get('end_exclusive')!=session:
        raise ValueError('Retained historical feed/window mismatch')
    if not timestamp(history['download_started_utc'])<=timestamp(history['prepared_utc'])<=timestamp(record['received_utc']):
        raise ValueError('Retained historical receipt chronology mismatch')
    target=work/'history'/session
    for field,suffix in [('history_files','.csv'),('metadata_files','.metadata.json')]:
        h=history.get(field,{})
        if len(h)!=len(SYMBOLS) or {PurePosixPath(p.replace('\\','/')).name for p in h}!={s+suffix for s in SYMBOLS}:
            raise ValueError('Complete retained fixed-universe history required')
        for original,sha in h.items():
            save_once_or_identical(target/PurePosixPath(original.replace('\\','/')).name,retained_file(files,original,sha))
    prior,quality=load_observations(target)
    if quality!=history['observations'] or any(d>=session for days in prior.values() for d in days):
        raise ValueError('Retained prior observation provenance mismatch')
    actions=snapshots['corporate_actions']
    if not actions or actions[-1].get('next_page_token') is not None: raise ValueError('Incomplete retained split pagination')
    events=events_from_pages(actions,SYMBOLS)
    if any(e['ex_date']>session for e in events): raise ValueError('Future split in retained receipt')
    current=opening_observations(snapshots['opening'],session)
    combined={s:dict(prior[s],**{session:current[s]}) for s in SYMBOLS}
    actual=infer(directory,combined,events,session)
    saved=snapshots['inference']
    if saved.get('orders') is not False or saved.get('session')!=session or actual['input_quality']!=saved['input_quality']:
        raise ValueError('Retained inference/input quality mismatch')
    compare_predictions(actual['predictions'],record['predictions'])
    compare_predictions(actual['predictions'],[dict(symbol=r['symbol'],probabilities=r['probabilities']) for r in saved['predictions']])
    if [r['signal_price'] for r in actual['predictions']]!=[r['signal_price'] for r in saved['predictions']]:
        raise ValueError('Retained decision prices changed')
    return dict(session=session,predictions=actual['predictions'],raw_opening=snapshots['opening'],
        calendar=snapshots['calendar'],input_predictions_reproduced=True,
        record_sha256=packet['record_sha256'],orders=False)


def outcome_market(raw_opening,raw_outcome,session):
    """No future full-session completeness filter: missing selected bars stay unknown."""
    import pandas as pd
    from macro_context_research import proxy_sessions
    if raw_outcome.get('next_page_token') or set(raw_outcome.get('bars',{}))!=set(SYMBOLS):
        raise ValueError('Complete outcome response pagination/universe required')
    current=opening_observations(raw_opening,session);market={}
    for symbol,records in raw_outcome['bars'].items():
        frame=pd.DataFrame([dict(symbol=symbol,timestamp=r['t'],open=r['o'],high=r['h'],low=r['l'],close=r['c'],volume=r['v']) for r in records])
        days=proxy_sessions(frame,symbol)
        if set(days)!={session}: raise ValueError('Wrong outcome date')
        regular=days[session]
        opening=regular.loc[regular.minute<600]
        if (opening.minute.tolist()!=list(range(570,600)) or
            not np.array_equal(opening[['open','high','low','close','volume']].to_numpy(),current[symbol][['open','high','low','close','volume']].to_numpy())):
            raise ValueError('Outcome opening revised or does not match captured information')
        if (regular.minute>677).any(): raise ValueError('Outcome response beyond fixed108-minute audit window')
        market[symbol]={int(r.minute)-570:np.asarray([r.open,r.high,r.low,r.close,r.volume],dtype=float) for r in regular.itertuples()}
    return market
