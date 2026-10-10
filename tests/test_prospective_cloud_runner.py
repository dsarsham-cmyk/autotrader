from datetime import datetime
import hashlib
import io
from pathlib import Path
import tarfile
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import prospective_cloud_runner as cloud
import prospective_forecast_evidence as evidence


@pytest.mark.parametrize('stamp,expected',[
    ('2026-10-12T13:57:00+00:00',True),('2026-10-12T14:57:00+00:00',False),
    ('2026-11-03T14:57:00+00:00',True),('2026-11-03T13:57:00+00:00',False),
    ('2026-10-10T13:57:00+00:00',False),('2026-10-12T14:16:00+00:00',False)])
def test_preparation_window_dst_and_late_skip(stamp,expected):
    assert cloud.eligible_plan(datetime.fromisoformat(stamp),'2026-10-12') is expected


def test_source_hash_portable_but_artifact_hash_byte_exact(tmp_path):
    a=tmp_path/'a.py';b=tmp_path/'b.py'
    a.write_bytes(b'print(1)\n');b.write_bytes(b'print(1)\r\n')
    assert evidence.source_digest(a)==evidence.source_digest(b)
    assert evidence.file_digest(a)!=evidence.file_digest(b)


def test_private_raw_data_encrypted_authenticated_and_recoverable(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cloud,'ROOT',Path('control'))
    receipts=Path('control/receipts');receipts.mkdir(parents=True)
    marker=b'private-provider-raw-data'
    (receipts/'raw.json').write_bytes(marker)
    history=Path('history');history.mkdir();(history/'AAPL.csv').write_text('retained-history')
    cloud.seal_evidence(history,'test-only-high-entropy-key')
    encrypted=Path('research_runs/private_evidence.aesgcm').read_bytes()
    assert marker not in encrypted
    key=hashlib.sha256(b'autotrader-prospective-evidence-v1\0test-only-high-entropy-key').digest()
    plaintext=AESGCM(key).decrypt(encrypted[:12],encrypted[12:],b'autotrader-prospective-evidence-v1')
    with tarfile.open(fileobj=io.BytesIO(plaintext),mode='r:gz') as tar:
        assert tar.extractfile('control/receipts/raw.json').read()==marker
    damaged=bytearray(encrypted);damaged[-1]^=1
    with pytest.raises(Exception):
        AESGCM(key).decrypt(bytes(damaged[:12]),bytes(damaged[12:]),b'autotrader-prospective-evidence-v1')
