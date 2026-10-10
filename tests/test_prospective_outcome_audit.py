from datetime import datetime,timedelta
import hashlib
import numpy as np
import pytest
from prospective_forecast_evidence import digest
from prospective_outcome_audit import anchor_check,evaluate_simulated_session,verify_archive,save_once_or_identical


def fixture(probability=.7):
    manifest=dict(created_utc='2026-10-10T14:00:00+00:00',forward_start='2026-10-12',
        trained_through='2026-10-01',feature_cutoff_minute=30,information_delay_minutes=15,
        execution_latency_minutes=1,feed='sip')
    envelope=dict(manifest=manifest,manifest_sha256=digest(manifest))
    record=dict(session_date='2026-10-12',captured_utc='2026-10-12T14:15:10+00:00',
        hypothetical_entry_not_before_utc='2026-10-12T14:16:00+00:00',manifest_sha256=envelope['manifest_sha256'],
        broker_orders_enabled=False,production_approved=False,predictions=[dict(symbol='AAPL',probability=probability)],
        input_receipt=dict(feed='sip',feature_cutoff_utc='2026-10-12T14:00:00+00:00',
            last_bar_end_utc='2026-10-12T14:00:00+00:00',received_utc='2026-10-12T14:15:05+00:00'))
    packet=dict(record=record,record_sha256=digest(record))
    metadata=dict(id=1,created_at='2026-10-12T14:15:30+00:00',verified_upload_completed_at='2026-10-12T14:15:31+00:00')
    start=datetime.fromisoformat('2026-10-12T13:30:00+00:00')
    raw=dict(bars={'AAPL':[dict(t=(start+timedelta(minutes=i)).isoformat(),o=100,h=100.2,l=99.8,c=100,v=1000) for i in range(30)]})
    bars={'AAPL':np.tile([100.,100.2,99.8,100,1000],(390,1))}
    bars['AAPL'][60,1]=101
    return packet,metadata,envelope,raw,bars


def test_synthetic_target_win_is_not_independent_validation():
    report=evaluate_simulated_session(*fixture())
    assert report['outcomes'][0]['active_day_win_rate_pct']==100
    assert report['outcomes'][0]['active_days']==1
    assert report['category_budget_pass'] and report['stock_budget_pass'] and report['max_positions_pass']
    assert not report['independent_validation_pass'] and not report['production_approved']


def test_no_trade_does_not_become_winning_day():
    report=evaluate_simulated_session(*fixture(.1))
    assert report['outcomes'][0]['active_days']==0
    assert report['outcomes'][0]['active_day_win_rate_pct'] is None


def test_late_anchor_not_forward_evidence():
    packet,metadata,envelope,raw,bars=fixture()
    metadata['created_at']='2026-10-12T14:16:01+00:00'
    metadata['verified_upload_completed_at']='2026-10-12T14:16:01+00:00'
    assert not anchor_check(packet,metadata,envelope)['timely_external_anchor']
    with pytest.raises(ValueError): evaluate_simulated_session(packet,metadata,envelope,raw,bars)


def test_altered_hypothetical_entry_cannot_buy_extra_anchor_time():
    packet,metadata,envelope,_,_=fixture()
    packet['record']['hypothetical_entry_not_before_utc']='2026-10-12T20:00:00+00:00'
    packet['record_sha256']=digest(packet['record'])
    with pytest.raises(ValueError): anchor_check(packet,metadata,envelope)


def test_original_input_and_outcome_prefix_must_match():
    packet,metadata,envelope,raw,bars=fixture()
    bars['AAPL'][0,3]=101
    with pytest.raises(ValueError): evaluate_simulated_session(packet,metadata,envelope,raw,bars)


def test_earlier_session_not_prospective():
    packet,metadata,envelope,_,_=fixture()
    packet['record']['session_date']='2026-10-01';packet['record_sha256']=digest(packet['record'])
    with pytest.raises(ValueError): anchor_check(packet,metadata,envelope)


def test_artifact_digest_mismatch_rejected():
    raw=b'own-archive';metadata={'digest':'sha256:'+hashlib.sha256(raw).hexdigest()}
    assert verify_archive(metadata,raw)==metadata['digest']
    with pytest.raises(ValueError): verify_archive(metadata,raw+b'changed')


def test_backups_retry_identically_but_never_overwrite_changed_evidence(tmp_path):
    path=tmp_path/'backup.zip'
    save_once_or_identical(path,b'first');save_once_or_identical(path,b'first')
    with pytest.raises(ValueError): save_once_or_identical(path,b'different')


def test_early_creation_does_not_prove_timely_upload_completion():
    packet,metadata,envelope,_,_=fixture()
    metadata['verified_upload_completed_at']='2026-10-12T14:16:10+00:00'
    assert not anchor_check(packet,metadata,envelope)['timely_external_anchor']
    del metadata['verified_upload_completed_at']
    assert not anchor_check(packet,metadata,envelope)['timely_external_anchor']
