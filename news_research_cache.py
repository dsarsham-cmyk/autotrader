"""GET-only private news archive. Timestamps are not original-delivery proof."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import requests
from dotenv import load_dotenv
from active_stock_research import SYMBOLS
from prospective_outcome_audit import save_once_or_identical

URL='https://data.alpaca.markets/v1beta1/news'
START='2024-01-01T00:00:00Z';END='2026-10-02T00:00:00Z'
_lock=threading.Lock();_next=0.


def intervals():
    edges=[f'{y:04d}-{m:02d}-01T00:00:00Z' for y in range(2024,2027) for m in range(1,13)
        if START<=f'{y:04d}-{m:02d}-01T00:00:00Z'<END]+[END]
    return list(zip(edges,edges[1:]))


def throttle():
    global _next
    with _lock:
        now=time.monotonic();wait=max(0,_next-now);_next=max(_next,now)+.5
    if wait: time.sleep(wait)


def fetch_chunk(root,left,right,auth):
    folder=root/left[:7];folder.mkdir(parents=True,exist_ok=True)
    token=None;seen=set();pages=[];articles=0
    for number in range(1,10001):
        params=dict(start=left,end=right,symbols=','.join(SYMBOLS),sort='asc',
            limit=50,include_content='false',exclude_contentless='false')
        if token: params['page_token']=token
        target=folder/f'{number:05d}.json';receipt=folder/f'{number:05d}.metadata.json'
        if target.exists():
            if not receipt.exists(): raise ValueError('Raw news page has no receipt')
            raw=target.read_bytes();meta=json.loads(receipt.read_text())
            if meta['params']!=params or meta['sha256']!=hashlib.sha256(raw).hexdigest():
                raise ValueError('News page provenance mismatch')
        else:
            if receipt.exists(): raise ValueError('News receipt has no raw page')
            for attempt in range(3):
                throttle();response=requests.get(URL,headers=auth,params=params,timeout=30)
                if response.status_code==200: break
                if response.status_code not in (429,500,502,503,504):
                    raise RuntimeError(f'News GET HTTP {response.status_code}; no fallback or purchase')
                time.sleep(5*(attempt+1))
            else: raise RuntimeError('News GET retry limit exceeded')
            raw=response.content
            meta=dict(url=URL,params=params,http_status=200,sha256=hashlib.sha256(raw).hexdigest(),
                received_utc=datetime.now(timezone.utc).isoformat())
            save_once_or_identical(target,raw)
            save_once_or_identical(receipt,json.dumps(meta,sort_keys=True).encode())
        data=json.loads(raw)
        if not isinstance(data.get('news'),list): raise ValueError('Invalid news page')
        pages.append(dict(path=str(target.relative_to(root)),sha256=meta['sha256']))
        articles+=len(data['news']);token=data.get('next_page_token')
        if not token: break
        if token in seen: raise ValueError('Repeated news pagination token')
        seen.add(token)
    else: raise ValueError('Incomplete news pagination')
    result=dict(start=left,end=right,pages=pages,article_rows=articles,complete=True)
    print(json.dumps(dict(news_month=left[:7],pages=len(pages),article_rows=articles)),flush=True)
    return result


def download(root):
    load_dotenv();root.mkdir(parents=True,exist_ok=True)
    auth={'APCA-API-KEY-ID':os.environ['ALPACA_API_KEY'],'APCA-API-SECRET-KEY':os.environ['ALPACA_API_SECRET']}
    report=dict(status='running_private_historical_news_download',symbols=list(SYMBOLS),
        start=START,end=END,chunks=[],include_content=False,orders=False,
        original_delivery_authenticated=False,independent_validation_pass=False,
        limitations=['Provider historical timestamps and latest text do not prove original timely receipt',
            'Intervals and ordering follow provider API; revised original texts are not recovered',
            'Fixed current stock universe; metadata-only news coverage does not prove forecasting advantage'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        for chunk in pool.map(lambda bounds:fetch_chunk(root,*bounds,auth),intervals()):
            report['chunks'].append(chunk)
            (root/'manifest.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_private_historical_news_download'
    report['total_page_rows']=sum(c['article_rows'] for c in report['chunks'])
    report['source_sha256']=hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    (root/'manifest.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


def load_news(root):
    report=json.loads((root/'manifest.json').read_text())
    if report['status']!='completed_private_historical_news_download':
        raise ValueError('Complete source archive required')
    if report['symbols']!=list(SYMBOLS) or (report['start'],report['end'])!=(START,END):
        raise ValueError('Unexpected fixed source query')
    if [(c['start'],c['end']) for c in report['chunks']]!=intervals():
        raise ValueError('Missing or duplicate source interval')
    records={}
    for chunk in report['chunks']:
        if not chunk['complete']: raise ValueError('Incomplete source chunk')
        for page in chunk['pages']:
            raw=(root/page['path']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=page['sha256']: raise ValueError('News source digest mismatch')
            for item in json.loads(raw)['news']:
                key=item['id']
                if key in records and records[key]!=item:
                    raise ValueError('Contradictory article revisions; do not choose silently')
                records[key]=item
    return list(records.values()),report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('cache/news_context'))
    a=p.parse_args();download(a.output)
