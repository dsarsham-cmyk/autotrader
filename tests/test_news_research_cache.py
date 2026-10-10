import hashlib
import json
from pathlib import Path
import pytest
import news_research_cache as news


def test_intervals_cover_predeclared_period_without_gaps():
    dates=news.intervals()
    assert dates[0][0]==news.START and dates[-1][1]==news.END
    assert all(a[1]==b[0] for a,b in zip(dates,dates[1:]))


def test_fetch_pages_use_get_and_retained_receipts_not_refetch(monkeypatch,tmp_path):
    class Response:
        status_code=200
        content=b'{"news":[{"id":1}],"next_page_token":null}'
    calls=[]
    def get(url,headers,params,timeout):
        calls.append(params);return Response()
    monkeypatch.setattr(news.requests,'get',get);monkeypatch.setattr(news,'throttle',lambda:None)
    before=news.fetch_chunk(tmp_path,*news.intervals()[0],{})
    after=news.fetch_chunk(tmp_path,*news.intervals()[0],{})
    assert before==after and len(calls)==1 and calls[0]['include_content']=='false'
    raw=tmp_path/before['pages'][0]['path'];raw.write_bytes(b'changed')
    with pytest.raises(ValueError,match='provenance'): news.fetch_chunk(tmp_path,*news.intervals()[0],{})


def test_http_denial_stops_without_fallback(monkeypatch,tmp_path):
    class Response: status_code=403
    monkeypatch.setattr(news.requests,'get',lambda *a,**k:Response())
    monkeypatch.setattr(news,'throttle',lambda:None)
    with pytest.raises(RuntimeError,match='no fallback or purchase'):
        news.fetch_chunk(tmp_path,*news.intervals()[0],{})


def test_repeated_token_rejected(monkeypatch,tmp_path):
    class Response:
        status_code=200;content=b'{"news":[],"next_page_token":"same"}'
    monkeypatch.setattr(news.requests,'get',lambda *a,**k:Response())
    monkeypatch.setattr(news,'throttle',lambda:None)
    with pytest.raises(ValueError,match='Repeated'): news.fetch_chunk(tmp_path,*news.intervals()[0],{})


def test_partial_archive_never_loaded_as_complete(tmp_path):
    (tmp_path/'manifest.json').write_text(json.dumps(dict(status='running_private_historical_news_download')))
    with pytest.raises(ValueError,match='Complete'): news.load_news(tmp_path)


def archive(tmp_path,payloads):
    chunks=[dict(start=a,end=b,complete=True,pages=[]) for a,b in news.intervals()]
    for i,data in enumerate(payloads):
        path=tmp_path/f'{i}.json';raw=json.dumps(dict(news=data)).encode();path.write_bytes(raw)
        chunks[0]['pages'].append(dict(path=path.name,sha256=hashlib.sha256(raw).hexdigest()))
    report=dict(status='completed_private_historical_news_download',symbols=list(news.SYMBOLS),
        start=news.START,end=news.END,chunks=chunks)
    (tmp_path/'manifest.json').write_text(json.dumps(report))


def test_archive_duplicates_identical_but_contradictory_revisions_rejected(tmp_path):
    archive(tmp_path,[[dict(id=1,headline='a')],[dict(id=1,headline='a')]])
    records,_=news.load_news(tmp_path);assert len(records)==1
    archive(tmp_path,[[dict(id=1,headline='a')],[dict(id=1,headline='b')]])
    with pytest.raises(ValueError,match='Contradictory'): news.load_news(tmp_path)


def test_archive_hash_and_complete_interval_coverage_required(tmp_path):
    archive(tmp_path,[[dict(id=1)]])
    (tmp_path/'0.json').write_bytes(b'changed')
    with pytest.raises(ValueError,match='digest'): news.load_news(tmp_path)
    archive(tmp_path,[[dict(id=1)]])
    m=json.loads((tmp_path/'manifest.json').read_text());m['chunks'].pop()
    (tmp_path/'manifest.json').write_text(json.dumps(m))
    with pytest.raises(ValueError,match='interval'): news.load_news(tmp_path)
