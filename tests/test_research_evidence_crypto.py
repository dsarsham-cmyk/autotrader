import base64
import os
import pytest
import research_evidence_crypto as crypto


def test_v2_key_and_envelope_independent_of_broker_secret(monkeypatch):
    key=b'x'*32
    monkeypatch.setenv(crypto.SECRET_NAME,base64.b64encode(key).decode())
    monkeypatch.setenv('ALPACA_API_SECRET','public-compromised-fixture')
    encrypted=crypto.encrypt_bytes(b'private-fixture',crypto.evidence_key())
    assert encrypted.startswith(crypto.MAGIC)
    assert crypto.decrypt_bytes(encrypted,key)==b'private-fixture'
    with pytest.raises(Exception): crypto.decrypt_bytes(encrypted,b'y'*32)


def test_missing_dedicated_key_never_falls_back_to_broker_key(tmp_path,monkeypatch):
    monkeypatch.delenv(crypto.SECRET_NAME,raising=False)
    monkeypatch.setenv('ALPACA_API_SECRET','fixture-broker-secret')
    monkeypatch.setattr(crypto,'KEY_PATH',tmp_path/'absent.dpapi')
    with pytest.raises(ValueError,match='no broker-secret fallback'): crypto.evidence_key()


@pytest.mark.skipif(os.name!='nt',reason='Windows DPAPI only')
def test_dpapi_protected_current_user_roundtrip():
    value=b'fake-test-only-evidence-key'
    protected=crypto.dpapi(value)
    assert value not in protected
    assert crypto.dpapi(protected,protect=False)==value
