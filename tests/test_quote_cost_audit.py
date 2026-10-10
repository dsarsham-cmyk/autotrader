import pytest
from quote_cost_audit import fetch_pages,summarize


def q(second,bid=100,ask=100.02):
    return dict(t=f'2026-01-01T10:00:{second:02d}Z',bp=bid,ap=ask,bs=1,**{'as':1})


def test_all_pages_consumed():
    calls=[]
    def get(params):
        calls.append(params)
        return dict(quotes={'A':[q(len(calls))]},next_page_token='next' if len(calls)==1 else None)
    result=fetch_pages(get,'A','start','end')
    assert result['pagination_complete'] and len(result['quotes'])==2
    assert calls[1]['page_token']=='next'


def test_repeated_token_is_not_complete():
    with pytest.raises(ValueError):
        fetch_pages(lambda p:dict(quotes={},next_page_token='same'),'A','start','end')


def test_stale_quote_is_not_full_coverage():
    result=summarize([q(0)],q(0)['t'],q(10)['t'])
    assert result['fresh_coverage_pct']==pytest.approx(20)


def test_crossed_quote_interrupts_coverage():
    result=summarize([q(0),q(1,101,100),q(3)],q(0)['t'],q(5)['t'])
    assert result['invalid_quotes']==1
    assert result['fresh_coverage_pct']==pytest.approx(60)


def test_time_weighting_not_update_count():
    quotes=[q(0,100,100.01),q(1,100,100.01),q(2,100,101)]
    result=summarize(quotes,q(0)['t'],q(10)['t'],max_age_seconds=10)
    assert result['fresh_coverage_pct']==100
    assert result['time_weighted_full_spread_median_bps']>90


def test_empty_not_zero_cost():
    result=summarize([],q(0)['t'],q(10)['t'])
    assert result['fresh_coverage_pct']==0
    assert result['time_weighted_full_spread_median_bps'] is None
