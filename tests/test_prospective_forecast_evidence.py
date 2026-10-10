from datetime import datetime,timezone,timedelta
import json
import pytest
import prospective_forecast_evidence as evidence


def clock(monkeypatch,value):
    monkeypatch.setattr(evidence,'utc_now',lambda:datetime.fromisoformat(value))


def setup(tmp_path,monkeypatch):
    artifact=tmp_path/'model';artifact.write_bytes(b'own-model-artifact')
    source=tmp_path/'source.py';source.write_text('own-source')
    clock(monkeypatch,'2026-10-10T13:00:00+00:00')
    evidence.freeze(tmp_path/'ledger',artifact,[source],'2026-10-01','2026-10-12')
    clock(monkeypatch,'2026-10-12T14:15:20+00:00')
    start=datetime.fromisoformat('2026-10-12T13:30:00+00:00')
    raw=tmp_path/'raw.json';raw.write_text(json.dumps(dict(bars={'AAPL':[
        dict(t=(start+timedelta(minutes=i)).isoformat(),o=100,h=101,l=99,c=100,v=1000)
        for i in range(30)]},next_page_token=None)))
    calendar=tmp_path/'calendar.json';calendar.write_text('[{"date":"2026-10-12"}]')
    receipt=dict(feed='sip',calendar_session_date='2026-10-12',
        feature_cutoff_utc='2026-10-12T14:00:00+00:00',last_bar_end_utc='2026-10-12T14:00:00+00:00',
        received_utc='2026-10-12T14:15:10+00:00',raw_response_sha256=evidence.file_digest(raw),
        calendar_response_sha256=evidence.file_digest(calendar),raw_response_path=str(raw),calendar_response_path=str(calendar))
    predictions=[dict(symbol='AAPL',probability=.6,mean_return=-.001,q10_return=-.01)]
    return artifact,source,receipt,predictions


def test_capture_once_and_no_claim_of_independent_authentication(tmp_path,monkeypatch):
    artifact,_,receipt,predictions=setup(tmp_path,monkeypatch)
    evidence.capture(tmp_path/'ledger',artifact,'2026-10-12',receipt,predictions)
    assert evidence.inspect(tmp_path/'ledger')['recorded_sessions']==1
    assert not evidence.inspect(tmp_path/'ledger')['independent_validation_pass']
    with pytest.raises(FileExistsError):
        evidence.capture(tmp_path/'ledger',artifact,'2026-10-12',receipt,predictions)


@pytest.mark.parametrize('now',['2026-10-12T14:14:59+00:00','2026-10-12T14:16:00+00:00',
    '2026-10-13T14:15:20+00:00'])
def test_early_late_or_backdated_forecasts_rejected(tmp_path,monkeypatch,now):
    artifact,_,receipt,predictions=setup(tmp_path,monkeypatch)
    clock(monkeypatch,now)
    with pytest.raises(ValueError): evidence.capture(tmp_path/'ledger',artifact,'2026-10-12',receipt,predictions)


@pytest.mark.parametrize('key,value',[('feed','iex'),('received_utc','2026-10-12T14:15:30+00:00'),
    ('last_bar_end_utc','2026-10-12T14:01:00+00:00'),('raw_response_sha256','missing'),
    ('calendar_session_date','2026-10-13')])
def test_invalid_input_evidence_rejected(tmp_path,monkeypatch,key,value):
    artifact,_,receipt,predictions=setup(tmp_path,monkeypatch)
    receipt[key]=value
    with pytest.raises(ValueError): evidence.capture(tmp_path/'ledger',artifact,'2026-10-12',receipt,predictions)


@pytest.mark.parametrize('which',['artifact','source'])
def test_changed_model_or_code_rejected(tmp_path,monkeypatch,which):
    artifact,source,receipt,predictions=setup(tmp_path,monkeypatch)
    (artifact if which=='artifact' else source).write_text('changed')
    with pytest.raises(ValueError): evidence.capture(tmp_path/'ledger',artifact,'2026-10-12',receipt,predictions)


def test_forecast_packet_tampering_detected(tmp_path,monkeypatch):
    artifact,_,receipt,predictions=setup(tmp_path,monkeypatch)
    evidence.capture(tmp_path/'ledger',artifact,'2026-10-12',receipt,predictions)
    path=tmp_path/'ledger'/'predictions'/'2026-10-12.json'
    packet=json.loads(path.read_text());packet['record']['predictions'][0]['probability']=.99
    path.write_text(json.dumps(packet))
    with pytest.raises(ValueError): evidence.inspect(tmp_path/'ledger')


def test_freeze_cannot_replace_existing_manifest(tmp_path,monkeypatch):
    artifact,source,_,_=setup(tmp_path,monkeypatch)
    clock(monkeypatch,'2026-10-10T13:00:00+00:00')
    with pytest.raises(FileExistsError): evidence.freeze(tmp_path/'ledger',artifact,[source],'2026-10-01','2026-10-12')


def test_future_training_or_nonfuture_start_rejected(tmp_path,monkeypatch):
    artifact,source,_,_=setup(tmp_path,monkeypatch)
    clock(monkeypatch,'2026-10-10T13:00:00+00:00')
    with pytest.raises(ValueError): evidence.freeze(tmp_path/'other',artifact,[source],'2026-10-13','2026-10-12')
    with pytest.raises(ValueError): evidence.freeze(tmp_path/'other',artifact,[source],'2026-10-01','2026-10-10')


def test_raw_input_changed_after_receipt_rejected(tmp_path,monkeypatch):
    artifact,_,receipt,predictions=setup(tmp_path,monkeypatch)
    from pathlib import Path
    Path(receipt['raw_response_path']).write_text('changed raw observations')
    with pytest.raises(ValueError): evidence.capture(tmp_path/'ledger',artifact,'2026-10-12',receipt,predictions)


def test_future_bar_rejected_even_if_receipt_claims_earlier_cutoff(tmp_path,monkeypatch):
    artifact,_,receipt,predictions=setup(tmp_path,monkeypatch)
    from pathlib import Path
    path=Path(receipt['raw_response_path']);payload=json.loads(path.read_text())
    payload['bars']['AAPL'][-1]['t']='2026-10-12T14:10:00+00:00'
    path.write_text(json.dumps(payload));receipt['raw_response_sha256']=evidence.file_digest(path)
    with pytest.raises(ValueError): evidence.capture(tmp_path/'ledger',artifact,'2026-10-12',receipt,predictions)
