import hashlib
import json
import pandas as pd
import pytest
import hybrid_iex_research as hybrid


def quote(second,bid=101,ask=101.02):
    return dict(t=f'2026-10-01T14:15:{second:02d}Z',bp=bid,ap=ask,bs=9,**{'as':1})


def test_mixed_feed_timing_preserves_context_delay_and_anchor_budget():
    start,end,context,entry=hybrid.bounds('2026-10-01')
    assert context.hour==14 and context.minute==0
    assert end-context==pd.Timedelta(minutes=15,seconds=30)
    assert entry-end==pd.Timedelta(seconds=30) and entry.minute==16
    assert end-start==pd.Timedelta(seconds=10)
    assert hybrid.bounds('2026-01-02')[2].hour==15


def test_future_quote_cannot_reprice_signal_or_last_observed_state():
    quotes=[quote(29)];end=hybrid.bounds('2026-10-01')[1]
    before=hybrid.latest_state(quotes,end)
    after=hybrid.latest_state(quotes+[quote(30,bid=200,ask=201)],end)
    assert before==after and before['mid']==pytest.approx(101.01)
    assert pd.Timestamp(before['timestamp'])<end


def test_stale_ambiguous_or_naive_quote_is_not_live_state():
    end=hybrid.bounds('2026-10-01')[1]
    assert hybrid.latest_state([quote(25)],end) is None
    assert hybrid.latest_state([quote(29),quote(29,bid=99,ask=100)],end) is None
    q=quote(29);q['t']='2026-10-01T14:15:29'
    with pytest.raises(ValueError,match='Aware'): hybrid.latest_state([q],end)


def test_all_iex_symbols_and_pages_used_without_feed_fallback():
    calls=[]
    def get(params):
        calls.append(params)
        return dict(quotes={'A':[quote(20)]} if len(calls)==1 else {'B':[quote(21)]},
            next_page_token='next' if len(calls)==1 else None)
    start,end,_,_=hybrid.bounds('2026-10-01')
    result=hybrid.fetch_batch(get,start,end,['A','B'])
    assert result['pagination_complete'] and result['pages']==2
    assert len(result['quotes']['A'])==len(result['quotes']['B'])==1
    assert all(call['feed']=='iex' for call in calls)
    assert calls[1]['page_token']=='next' and pd.Timestamp(calls[0]['end'])<end


def test_repeated_pagination_token_or_wrong_symbol_fails_closed():
    start,end,_,_=hybrid.bounds('2026-10-01')
    with pytest.raises(ValueError,match='Repeated'):
        hybrid.fetch_batch(lambda p:dict(quotes={},next_page_token='same'),start,end,['A'])
    with pytest.raises(ValueError,match='Unexpected'):
        hybrid.fetch_batch(lambda p:dict(quotes={'WRONG':[]}),start,end,['A'])


def retained(tmp_path,monkeypatch,wide=False):
    date='2026-10-01';start,end,_,_=hybrid.bounds(date)
    raw=dict(identity=dict(date=date,symbols=hybrid.SYMBOLS,feed='iex',start=start.isoformat(),
        cutoff=end.isoformat(),seed_seconds=2),pagination_complete=True,
        quotes={'AAPL':[quote(i,ask=102 if wide else 101.02) for i in range(20,30)]})
    content=json.dumps(raw).encode();directory=tmp_path/'quotes';directory.mkdir()
    (directory/f'{date}.json').write_bytes(content)
    payload=dict(plan=dict(protocol=hybrid.PROTOCOL,dates=[date],bar_cache_sha256={'AAPL':'barhash'}),
        dates=[dict(date=date,status='complete_historical_iex',cache_sha256=hashlib.sha256(content).hexdigest())])
    (tmp_path/'collection_status.json').write_text(json.dumps(payload))
    original=dict(date=date,symbol='AAPL',features=[.01]*21,signal_price=100)
    monkeypatch.setattr(hybrid,'load_universe',lambda p:({},dict(hashes={'AAPL':'barhash'})))
    monkeypatch.setattr(hybrid,'extended_rows',lambda p:[original])
    return original


def test_fresh_signal_fixes_both_arm_limits_without_future_open(tmp_path,monkeypatch):
    original=retained(tmp_path,monkeypatch)
    rows,_,evidence=hybrid.matched_rows(tmp_path,tmp_path)
    assert len(rows)==1 and rows[0]['signal_price']==pytest.approx(101.01)
    assert original['signal_price']==100  # old context not rewritten
    assert rows[0]['quote_features'][-1]==pytest.approx(.0101)
    assert len(rows[0]['quote_features'])==10 and evidence['retained_candidates']==1
    assert pd.Timestamp(rows[0]['iex_cutoff_utc'])<pd.Timestamp(rows[0]['hypothetical_entry_utc'])


def test_wide_known_quote_spread_excludes_both_arms_before_prediction(tmp_path,monkeypatch):
    retained(tmp_path,monkeypatch,wide=True)
    rows,_,evidence=hybrid.matched_rows(tmp_path,tmp_path)
    assert not rows and len(evidence['exclusions'])==6


def test_changed_quote_bytes_not_reproduced_as_old_inputs(tmp_path,monkeypatch):
    retained(tmp_path,monkeypatch)
    path=tmp_path/'quotes'/'2026-10-01.json';path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError,match='Changed retained'):
        hybrid.matched_rows(tmp_path,tmp_path)


def test_partial_hybrid_collection_not_a_completed_experiment(tmp_path):
    (tmp_path/'collection_status.json').write_text(json.dumps(dict(plan=dict(protocol=hybrid.PROTOCOL,
        dates=['2026-10-01']),dates=[])))
    with pytest.raises(ValueError,match='Incomplete'):
        hybrid.matched_rows(tmp_path,tmp_path)
