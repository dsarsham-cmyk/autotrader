from datetime import datetime,timedelta
import hashlib
import io
import json
from pathlib import Path
import tarfile
import numpy as np
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import prospective_full_audit as audit


def encrypt_tar(name='receipts/raw.json',secret='fixture-secret'):
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w:gz') as tar:
        entry=tarfile.TarInfo(name);payload=b'own-data';entry.size=len(payload)
        tar.addfile(entry,io.BytesIO(payload))
    key=hashlib.sha256(b'autotrader-prospective-evidence-v1\0'+secret.encode()).digest()
    nonce=b'012345678901'
    return nonce+AESGCM(key).encrypt(nonce,buffer.getvalue(),b'autotrader-prospective-evidence-v1')


def test_authenticated_private_archive_and_wrong_key():
    encrypted=encrypt_tar()
    assert audit.decrypt_private_archive(encrypted,'fixture-secret')['receipts/raw.json']==b'own-data'
    with pytest.raises(Exception): audit.decrypt_private_archive(encrypted,'wrong-key')


@pytest.mark.parametrize('name',['../escape','/absolute'])
def test_unsafe_archive_paths_rejected_without_extraction(name):
    with pytest.raises(ValueError): audit.decrypt_private_archive(encrypt_tar(name),'fixture-secret')


def test_retained_input_hash_and_basename_uniqueness():
    value=b'original';sha=hashlib.sha256(value).hexdigest()
    assert audit.retained_file({'receipt/raw.json':value},'/runner/receipt/raw.json',sha)==value
    with pytest.raises(ValueError): audit.retained_file({'receipt/raw.json':value+b'changed'},'/raw.json',sha)
    with pytest.raises(ValueError): audit.retained_file({'a/raw.json':value,'b/raw.json':value},'/raw.json',sha)


def test_missing_history_prevents_forecast_reproduction(tmp_path,monkeypatch):
    model=tmp_path/'model.joblib';model.write_bytes(b'own-artifact')
    monkeypatch.setattr(audit,'read_manifest',lambda d:dict(manifest={'artifact_sha256':audit.file_digest(model)}))
    monkeypatch.setattr(audit,'source_matches',lambda m:True)
    monkeypatch.setattr(audit.joblib,'load',lambda p:dict(sklearn_version=audit.sklearn.__version__,
        features=audit.FEATURES+audit.EXTRA_FEATURES,mode='prospective_research_control_only',broker_orders_enabled=False))
    raw=json.dumps({'bars':{}}).encode();calendar=json.dumps([{'date':'2026-10-12'}]).encode()
    packet=dict(record=dict(session_date='2026-10-12',input_receipt=dict(
        raw_response_path='raw.json',raw_response_sha256=hashlib.sha256(raw).hexdigest(),
        calendar_response_path='calendar.json',calendar_response_sha256=hashlib.sha256(calendar).hexdigest())))
    with pytest.raises(ValueError,match='historical context'):
        audit.reproduce(packet,{'raw.json':raw,'calendar.json':calendar},tmp_path,tmp_path/'work')


def test_full_session_data_requires_original_minute_timestamps(tmp_path,monkeypatch):
    start=datetime.fromisoformat('2026-09-01T13:30:00+00:00')
    packet={'bars':{s:[dict(t=(start+timedelta(minutes=i)).isoformat(),o=100,h=101,l=99,c=100,v=1000)
        for i in range(390)] for s in audit.SYMBOLS}}
    packet['bars']['AAPL'][10]['t']=packet['bars']['AAPL'][9]['t']
    monkeypatch.setattr(audit,'get_json',lambda *a:packet)
    with pytest.raises(ValueError,match='outcome bars'):
        audit.completed_market_data('2026-09-01',tmp_path)


def test_model_tampering_checked_before_deserialization(tmp_path,monkeypatch):
    (tmp_path/'model.joblib').write_bytes(b'changed')
    monkeypatch.setattr(audit,'read_manifest',lambda d:dict(manifest={'artifact_sha256':'wrong'}))
    monkeypatch.setattr(audit,'source_matches',lambda m:True)
    monkeypatch.setattr(audit.joblib,'load',lambda p:pytest.fail('Do not deserialize changed model'))
    with pytest.raises(ValueError,match='artifact changed'):
        audit.reproduce({}, {},tmp_path,tmp_path/'work')


@pytest.mark.skipif(not Path('cache/prospective_history_v1/AAPL.csv').exists(),reason='Optional own historical cache unavailable')
def test_synthetic_roundtrip_actual_frozen_model_and_owned_history(tmp_path):
    import joblib
    prior,_=audit.load_universe(Path('cache/prospective_history_v1'))
    current={symbol:prior['2026-10-09'][symbol][0][:30] for symbol in audit.SYMBOLS}
    # Manufactured October-12 packet made from already observed October-9 bars.
    # This tests software only, NEVER independent/forward market evidence.
    session='2026-10-12';start=datetime.fromisoformat('2026-10-12T13:30:00+00:00')
    rows=audit.current_context(prior,current,session)
    model_dir=Path('research_prospective/control_v2')
    artifact=joblib.load(model_dir/'model.joblib')
    forecasts=audit.predict_forecasters(artifact['fitted'],rows)
    raw=json.dumps(dict(bars={symbol:[dict(t=(start+timedelta(minutes=i)).isoformat(),
        **{k:float(v) for k,v in zip(['o','h','l','c','v'],a[i])}) for i in range(30)]
        for symbol,a in current.items()},next_page_token=None)).encode()
    calendar=json.dumps([{'date':session}]).encode()
    files={'receipts/synthetic_bars.json':raw,'receipts/synthetic_calendar.json':calendar}
    history={}
    for symbol in audit.SYMBOLS:
        path=Path('cache/prospective_history_v1')/f'{symbol}.csv';content=path.read_bytes()
        files[f'history/{symbol}.csv']=content
        history[str(path)]=hashlib.sha256(content).hexdigest()
    receipt=dict(raw_response_path='synthetic_bars.json',raw_response_sha256=hashlib.sha256(raw).hexdigest(),
        calendar_response_path='synthetic_calendar.json',calendar_response_sha256=hashlib.sha256(calendar).hexdigest(),history_files=history)
    packet=dict(record=dict(session_date=session,input_receipt=receipt,predictions=[
        dict(symbol=row['symbol'],**{k:float(values[i]) for k,values in forecasts.items()}) for i,row in enumerate(rows)]))
    assert audit.reproduce(packet,files,model_dir,tmp_path)==json.loads(raw)
    packet['record']['predictions'][0]['probability']+=.001
    with pytest.raises(ValueError,match='not reproduced'):
        audit.reproduce(packet,files,model_dir,tmp_path)
