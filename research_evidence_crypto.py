"""Dedicated evidence encryption key; never reuse broker credentials.

Windows copy is DPAPI protected for the current user. GitHub receives a
LibSodium-sealed repository secret, not plaintext in source/history/logs.
"""
import argparse
import base64
import ctypes
from ctypes import wintypes
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import tarfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_PATH=Path('research_runs/keys/control_evidence_key.dpapi')
SECRET_NAME='PROSPECTIVE_EVIDENCE_KEY'
MAGIC=b'ATRE2\0'
AAD=b'autotrader-prospective-evidence-v2'


def dpapi(data,protect=True):
    if os.name!='nt': raise ValueError('Use environment secret outside Windows')
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(data)
    source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    library=ctypes.WinDLL('crypt32',use_last_error=True)
    function=library.CryptProtectData if protect else library.CryptUnprotectData
    function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,
        ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    function.restype=wintypes.BOOL
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try: return ctypes.string_at(target.data,target.size)
    finally:
        free=ctypes.WinDLL('kernel32').LocalFree
        free.argtypes=[ctypes.c_void_p];free.restype=ctypes.c_void_p
        free(ctypes.cast(target.data,ctypes.c_void_p))


def decode_key(value):
    key=base64.b64decode(value,validate=True)
    if len(key)!=32: raise ValueError('Dedicated 256-bit evidence key required')
    return key


def evidence_key():
    value=os.environ.get(SECRET_NAME)
    if value: return decode_key(value)
    if not KEY_PATH.exists(): raise ValueError('Dedicated evidence key unavailable; no broker-secret fallback')
    return decode_key(dpapi(KEY_PATH.read_bytes(),protect=False).decode())


def encrypt_bytes(plaintext,key):
    if len(key)!=32: raise ValueError('AES-256 key required')
    nonce=secrets.token_bytes(12)
    return MAGIC+nonce+AESGCM(key).encrypt(nonce,plaintext,AAD)


def decrypt_bytes(encrypted,key):
    if not encrypted.startswith(MAGIC) or len(encrypted)<len(MAGIC)+28:
        raise ValueError('Invalid v2 evidence envelope')
    nonce=encrypted[len(MAGIC):len(MAGIC)+12]
    return AESGCM(key).decrypt(nonce,encrypted[len(MAGIC)+12:],AAD)


def seal(directory,history):
    archive=io.BytesIO()
    with tarfile.open(fileobj=archive,mode='w:gz') as tar:
        for root in [directory/'receipts',history]:
            if root.exists():
                for path in sorted(root.rglob('*')):
                    if path.is_file(): tar.add(path,arcname=str(path),recursive=False)
    encrypted=encrypt_bytes(archive.getvalue(),evidence_key())
    path=Path('research_runs/private_evidence.aesgcm')
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(encrypted)
    print(json.dumps(dict(ciphertext_sha256=hashlib.sha256(encrypted).hexdigest(),
        encryption_version=2,broker_secret_used=False,raw_data_published=False)))


def provision():
    # Explicit provisioning mode is the only external write. It affects one
    # research-encryption secret, not any broker key/order/setting.
    import requests
    from nacl.public import PublicKey,SealedBox
    from prospective_outcome_audit import headers,BASE
    auth=headers();url=BASE+'/actions/secrets/'+SECRET_NAME
    existing=requests.get(url,headers=auth,timeout=20)
    if existing.status_code not in {200,404}: raise RuntimeError('Cannot inspect research secret')
    if existing.status_code==200 and not KEY_PATH.exists():
        raise ValueError('Existing remote key lacks local recovery copy; refusing replacement')
    if not KEY_PATH.exists():
        value=base64.b64encode(secrets.token_bytes(32))
        protected=dpapi(value)
        KEY_PATH.parent.mkdir(parents=True,exist_ok=True)
        with KEY_PATH.open('xb') as handle: handle.write(protected)
    value=dpapi(KEY_PATH.read_bytes(),protect=False)
    public=requests.get(BASE+'/actions/secrets/public-key',headers=auth,timeout=20)
    if public.status_code!=200: raise RuntimeError('Cannot fetch GitHub repository encryption key')
    key=public.json()
    encrypted=SealedBox(PublicKey(base64.b64decode(key['key']))).encrypt(value)
    result=requests.put(url,headers=auth,json=dict(key_id=key['key_id'],
        encrypted_value=base64.b64encode(encrypted).decode()),timeout=20)
    if result.status_code not in {201,204}: raise RuntimeError('Research secret provisioning unconfirmed')
    check=requests.get(url,headers=auth,timeout=20)
    print(json.dumps(dict(secret_name=SECRET_NAME,provision_http=result.status_code,
        remote_confirmed=check.status_code==200,local_copy='Windows user-protected DPAPI',broker_credentials_changed=False)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['seal','provision','validate'])
    args=parser.parse_args()
    if args.mode=='provision': provision()
    elif args.mode=='seal': seal(Path('research_prospective/control_v2'),Path('cache/cloud_prospective_history'))
    else:
        key=evidence_key();assert decrypt_bytes(encrypt_bytes(b'test-only',key),key)==b'test-only'
        print(json.dumps(dict(dedicated_encryption_roundtrip=True,broker_secret_used=False)))
