import copy
import pytest
from paper_fill_quote_audit import quote_match,select_activities


def activity(): return dict(id='a',activity_type='FILL',symbol='AAPL',transaction_time='2026-10-09T14:00:02Z',side='buy',price='100.02',qty='2')
def quote(stamp='2026-10-09T14:00:01Z',bid=100.,ask=100.02): return dict(t=stamp,bp=bid,ap=ask,bs=1,**{'as':1})


def test_future_quote_cannot_change_fill_comparison():
    before=quote_match(activity(),[quote()])
    after=quote_match(activity(),[quote(),quote('2026-10-09T14:00:03Z',50.,51.)])
    assert before==after and before['status']=='matched_paper_fill_quote'
    assert not before['total_real_cost_measured']


def test_last_invalid_or_conflicting_quote_does_not_fall_back_to_favorable_earlier():
    assert quote_match(activity(),[quote(),quote('2026-10-09T14:00:02Z',101.,100.)])['status']=='invalid_terminal_quote'
    quotes=[quote(),quote(bid=99.,ask=100.)]
    assert quote_match(activity(),quotes)['status']=='ambiguous_terminal_quote'
    assert quote_match(activity(),list(reversed(quotes)))==quote_match(activity(),quotes)


def test_stale_and_absent_quotes_remain_unknown():
    assert quote_match(activity(),[quote('2026-10-09T13:59:59Z')])['status']=='stale_terminal_quote'
    assert quote_match(activity(),[])['status']=='no_quote_at_or_before_fill'


def test_sell_fill_cost_sign_differs_from_buy():
    buy=activity();sell=dict(buy,side='sell',price='100.00')
    assert quote_match(buy,[quote()])['signed_fill_vs_contemporaneous_mid_bps']==pytest.approx(quote_match(sell,[quote()])['signed_fill_vs_contemporaneous_mid_bps'])


def test_activity_duplicate_or_wrong_order_not_silently_dropped():
    a=activity();assert select_activities([a])==[a]
    with pytest.raises(ValueError): select_activities([a,copy.deepcopy(a)])
    earlier=dict(a,id='b',transaction_time='2026-10-08T14:00:00Z')
    with pytest.raises(ValueError): select_activities([earlier,a])


def test_invalid_fill_and_timezone_rejected():
    with pytest.raises(ValueError): quote_match(dict(activity(),price='nan'),[quote()])
    with pytest.raises(ValueError): quote_match(dict(activity(),transaction_time='2026-10-09T14:00:02'),[quote()])
