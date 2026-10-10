import numpy as np
import pytest
from quote_microstructure_research import quote_features,bounds


def quote(second,bid=100,ask=100.02,bs=9,az=1):
    return dict(t=f'2026-01-01T10:00:{second:02d}Z',bp=bid,ap=ask,bs=bs,**{'as':az})


def test_future_quotes_cannot_change_features():
    quotes=[quote(i) for i in range(10)]
    before=quote_features(quotes,quote(0)['t'],quote(10)['t'])
    after=quote_features(quotes+[quote(10,bid=50,ask=51),quote(20,bid=200,ask=201)],quote(0)['t'],quote(10)['t'])
    assert before==after and before['status']=='usable'
    assert before['features'][0]==pytest.approx(.8)
    assert before['features'][4]>0  # bid-heavy weighted midpoint proxy


def test_time_weighting_not_quote_count_and_stale_fail_closed():
    result=quote_features([quote(0),quote(1,bs=1,az=9),quote(9,bs=1,az=9)],
        quote(0)['t'],quote(10)['t'],max_age=10)
    assert result['features'][0]==pytest.approx(-.64)
    stale=quote_features([quote(0)],quote(0)['t'],quote(10)['t'])
    assert stale['status']=='insufficient_quote_coverage' and stale['features'] is None


def test_invalid_and_ambiguous_timestamps_interrupt_known_coverage():
    quotes=[quote(i) for i in range(10)]
    quotes.append(quote(5,bid=101,ask=100))
    result=quote_features(quotes,quote(0)['t'],quote(10)['t'])
    assert result['fresh_coverage_pct']==pytest.approx(90)
    # No arbitrary 'last quote wins' at a conflicting timestamp.
    assert quote_features(list(reversed(quotes)),quote(0)['t'],quote(10)['t'])==result


def test_invalid_terminal_quote_cannot_supply_last_imbalance():
    quotes=[quote(i) for i in range(10)]
    quotes[-1]['bs']=0
    result=quote_features(quotes,quote(0)['t'],quote(10)['t'])
    assert not result['terminal_quote_fresh'] and result['features'] is None


def test_seed_before_window_not_older_history_or_future():
    quotes=[quote(0),quote(2),quote(3)]
    result=quote_features(quotes,quote(1)['t'],quote(4)['t'])
    assert result['fresh_coverage_pct']==100 and result['status']=='usable'
    assert np.isfinite(result['features']).all()


def test_window_cutoff_handles_new_york_dst():
    start,end=bounds('2026-10-01')
    assert end.hour==14 and (end-start).total_seconds()==10
    _,winter=bounds('2026-01-02');assert winter.hour==15
