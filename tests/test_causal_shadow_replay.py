from copy import deepcopy
from datetime import timedelta,timezone
import numpy as np
import pytest
import prospective_forecast_evidence as evidence
import causal_shadow_replay as replay
import causal_shadow_audit as audit
from tests.test_causal_shadow_collector import raw_packet


def anchor_fixture(monkeypatch):
    manifest=dict(forward_start='2026-10-12',trained_through='2026-10-01',created_utc='2026-10-10T18:00:00Z')
    protocol=dict(protocol_sha256='p',protocol=dict(created_utc='2026-10-10T19:00:00Z'))
    monkeypatch.setattr(replay,'validate',lambda d:(manifest,protocol))
    monkeypatch.setattr(evidence,'read_manifest',lambda d:dict(manifest_sha256='m'))
    run=dict(id=10,path='.github/workflows/causal-shadow-prospective.yml',status='completed',run_attempt=1,head_branch='main',head_sha='a'*40)
    record=dict(schema=1,session_date='2026-10-12',manifest_sha256='m',collector_protocol_sha256='p',
        orders=False,production_approved=False,workflow_run_id='10',source_workflow_sha='a'*40,
        captured_utc='2026-10-12T14:15:02Z',received_utc='2026-10-12T14:15:01Z',hypothetical_entry_not_before_utc='2026-10-12T14:16:00Z')
    meta=dict(id=20,workflow_run=dict(id=10,head_sha='a'*40),created_at='2026-10-12T14:15:03Z',verified_upload_completed_at='2026-10-12T14:15:05Z')
    return dict(record=record,record_sha256=evidence.digest(record)),meta,run


def test_external_anchor_needs_completed_upload_with_resolution_margin(monkeypatch):
    packet,meta,run=anchor_fixture(monkeypatch)
    assert replay.anchor_check(packet,meta,run,None)['timely_external_anchor']
    late=dict(meta,verified_upload_completed_at='2026-10-12T14:15:59Z')
    assert not replay.anchor_check(packet,late,run,None)['timely_external_anchor']
    del late['verified_upload_completed_at']
    assert not replay.anchor_check(packet,late,run,None)['timely_external_anchor']
    with pytest.raises(ValueError): replay.anchor_check(packet,meta,dict(run,run_attempt=2),None)
    with pytest.raises(ValueError): replay.anchor_check(packet,dict(meta,workflow_run=dict(id=11,head_sha='a'*40)),run,None)


def test_probabilities_and_forecast_chronology_cannot_be_forged(monkeypatch):
    packet,meta,run=anchor_fixture(monkeypatch)
    changed=deepcopy(packet);changed['record']['received_utc']='2026-10-12T14:14:59Z';changed['record_sha256']=evidence.digest(changed['record'])
    with pytest.raises(ValueError): replay.anchor_check(changed,meta,run,None)
    expected=[dict(symbol='AAPL',probabilities=dict(target_004=.65,target_010=.4))]
    replay.compare_predictions(expected,expected)
    for p in (True,float('nan'),1.1,.7):
        actual=deepcopy(expected);actual[0]['probabilities']['target_004']=p
        with pytest.raises(ValueError): replay.compare_predictions(expected,actual)
    with pytest.raises(ValueError): replay.compare_predictions(expected,expected+expected)


def test_future_price_missing_is_not_a_full_session_candidate_filter():
    opening=raw_packet();outcome=deepcopy(opening)
    start=audit.timing('2026-10-12')[0]
    for s,rows in outcome['bars'].items():
        rows.extend(dict(t=(start+timedelta(minutes=i)).astimezone(timezone.utc).isoformat(),o=100,h=101,l=99,c=100,v=1000) for i in range(30,108))
    del outcome['bars']['AAPL'][60]
    market=replay.outcome_market(opening,outcome,'2026-10-12')
    assert 60 not in market['AAPL'] and len(market)==20
    changed=deepcopy(outcome);changed['bars']['AAPL'][0]['v']=1001
    with pytest.raises(ValueError): replay.outcome_market(opening,changed,'2026-10-12')


def verified(date):
    return dict(session=date,predictions=[dict(symbol='AAPL',signal_price=100.,probabilities=dict(target_004=.9,target_010=.9))],
        market={'AAPL':{k:np.asarray([100.,100.5,99.9,100.,1000.]) for k in range(46,108)}})


def test_continuous_capital_missing_day_stops_not_reset_or_skip():
    dates=[dict(date=d) for d in ['2026-10-12','2026-10-13','2026-10-14']]
    result=audit.evaluate_series(dates,[verified(dates[0]['date']),verified(dates[2]['date'])])
    assert result['missing_completed_sessions']==['2026-10-13']
    assert result['unreplayed_later_verified_sessions']==['2026-10-14']
    assert all(o['profit_usd'] is None and [d['date'] for d in o['daily']]==['2026-10-12']
        for c in result['cases'] for o in c['outcomes'])
    assert not result['performance_screen_pass']
    complete=audit.evaluate_series(dates,[verified(r['date']) for r in dates])
    original=complete['cases'][0]['outcomes'][0]
    assert original['daily'][1]['equity']==pytest.approx(original['daily'][0]['equity']+original['daily'][1]['pnl'])
    assert not complete['performance_screen_pass']


def test_empty_no_eligible_duplicate_pending_and_unknown_selected_are_distinct():
    assert not audit.evaluate_series([],[])['performance_screen_pass']
    day=verified('2026-10-12');calendar=[dict(date=day['session'])]
    no_eligible=dict(day,predictions=[])
    inactive=audit.evaluate_series(calendar,[no_eligible])
    assert all(o['profit_usd']==0 and o['active_days']==0 for c in inactive['cases'] for o in c['outcomes'])
    duplicate=audit.evaluate_series(calendar,[day,day])
    assert duplicate['duplicate_forecast_sessions']==['2026-10-12']
    pending=audit.evaluate_series(calendar,[day],pending=True)
    assert all(o['profit_usd'] is None for c in pending['cases'] for o in c['outcomes'])
    del day['market']['AAPL'][60]
    unknown=audit.evaluate_series(calendar,[day])
    assert unknown['cases'][0]['outcomes'][0]['full_period_coverage_complete']
    assert unknown['cases'][1]['outcomes'][0]['profit_usd'] is None


def test_discovery_pagination_requires_all_items_and_no_duplicates():
    class Response:
        def __init__(self,data): self.data=data
        def json(self): return self.data
    with pytest.raises(ValueError): audit.pages('/x','items',{},lambda *a:Response(dict(items=[dict(id=1)],total_count=2)))
    with pytest.raises(ValueError): audit.pages('/x','items',{},lambda *a:Response(dict(items=[dict(id=1),dict(id=1)],total_count=2)))


def test_success_only_in_latency_stress_does_not_qualify_primary_policy():
    import pandas as pd
    dates=pd.bdate_range('2026-10-12',periods=100).strftime('%Y-%m-%d').tolist()
    accepted=[verified(d) for d in dates]
    for v in accepted:
        v['market']['AAPL'][46]=np.asarray([100.,100.5,98.,100.,1000.])
        v['market']['AAPL'][47]=np.asarray([100.,101.1,99.9,100.,1000.])
    result=audit.evaluate_series([dict(date=d) for d in dates],accepted)
    assert any(c['outcomes'][2]['performance_screen_pass'] for c in result['cases'])
    assert not result['performance_screen_pass']
    assert not result['independent_validation_pass'] and not result['production_approved']


def test_encrypted_synthetic_inputs_reproduce_actual_frozen_heads(monkeypatch,tmp_path):
    import io,json,tarfile
    import pandas as pd
    import prospective_full_audit as full
    from active_stock_research import SYMBOLS
    from causal_shadow_bundle import infer
    from causal_opening_inventory import load_observations
    from causal_shadow_collector import ROOT,opening_observations
    from research_evidence_crypto import encrypt_bytes
    dates=pd.bdate_range(end='2026-10-09',periods=25).strftime('%Y-%m-%d').tolist()
    histories={};metadata={};base=tmp_path/'source'
    for symbol in SYMBOLS:
        rows=[]
        for date in dates:
            start=audit.timing(date)[0]
            for minute in list(range(30))+[389]:
                rows.append(dict(symbol=symbol,timestamp=(start+timedelta(minutes=minute)).astimezone(timezone.utc).isoformat(),
                    open=100.,high=100.5,low=99.9,close=100.,volume=1000.))
        path=base/(symbol+'.csv');path.parent.mkdir(parents=True,exist_ok=True)
        pd.DataFrame(rows).to_csv(path,index=False)
        sha=evidence.file_digest(path);histories[str(path)]=sha
        meta=path.with_suffix('.metadata.json');evidence.write_once(meta,dict(feed='sip',adjustment='raw',sha256=sha,test_fixture_only=True))
        metadata[str(meta)]=evidence.file_digest(meta)
    prior,quality=load_observations(base);raw=raw_packet();current=opening_observations(raw,'2026-10-12')
    combined={s:dict(prior[s],**{'2026-10-12':current[s]}) for s in SYMBOLS}
    predicted=infer(ROOT,combined,[],'2026-10-12')
    snapshot=dict(opening=raw,calendar=[dict(date='2026-10-12',open='09:30',close='16:00')],
        corporate_actions=[dict(corporate_actions={},next_page_token=None)],inference=predicted,
        history_provenance=dict(feed='sip',adjustment='raw',end_exclusive='2026-10-12',history_files=histories,
            metadata_files=metadata,observations=quality,download_started_utc='2026-10-12T13:50:00Z',prepared_utc='2026-10-12T14:00:00Z'))
    refs={}
    for name,value in snapshot.items():
        path=tmp_path/'receipts'/f'2026-10-12_{name}.json';evidence.write_once(path,value)
        refs[name]=dict(path=str(path),sha256=evidence.file_digest(path))
    archive=io.BytesIO()
    with tarfile.open(fileobj=archive,mode='w:gz') as tar:
        for path in sorted(tmp_path.rglob('*')):
            if path.is_file(): tar.add(path,arcname=str(path.relative_to(tmp_path)),recursive=False)
    key=b'k'*32;monkeypatch.setattr(full,'evidence_key',lambda:key)
    files=full.decrypt_private_archive(encrypt_bytes(archive.getvalue(),key))
    packet=dict(record=dict(session_date='2026-10-12',received_utc='2026-10-12T14:15:01Z',receipts=refs,
        predictions=[dict(symbol=p['symbol'],probabilities=p['probabilities']) for p in predicted['predictions']]),record_sha256='fixture_not_prospective')
    result=replay.reproduce(packet,files,ROOT,tmp_path/'replay')
    assert result['input_predictions_reproduced'] and len(result['predictions'])==20
    assert result['record_sha256']=='fixture_not_prospective'  # Never a real anchored observation.
    changed=deepcopy(packet);changed['record']['predictions'][0]['probabilities']['target_004']=.99999
    with pytest.raises(ValueError): replay.reproduce(changed,files,ROOT,tmp_path/'replay')
