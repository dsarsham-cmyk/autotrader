import pytest
from research_calendar_audit import calendar_dates,inspect


def source(dates):
    return dict(cases=[dict(model='fixture',folds=[dict(test_first='2026-10-12',test_last='2026-10-13')],
        outcomes=[dict(threshold=.65,costs_bps=10,delay=16,full_period_coverage_complete=True,
            daily=[dict(date=d) for d in dates])])])


def calendar():
    rows=[dict(date='2026-10-12',open='09:30',close='16:00'),dict(date='2026-10-13',open='09:30',close='13:00')]
    return calendar_dates(rows,'2026-10-12','2026-10-13')


def test_half_day_retained_when_fixed_horizon_is_before_close():
    r=inspect(source(['2026-10-12','2026-10-13']),calendar())
    assert r['all_observed_spans_cover_calendar'] and r['cases'][0]['early_close_dates']==['2026-10-13']
    assert not r['independent_validation_pass'] and not r['orders']


def test_missing_day_invalidates_full_period_claim_not_counted_no_trade():
    r=inspect(source(['2026-10-12']),calendar())
    assert r['cases'][0]['missing_ledger_dates']==['2026-10-13']
    assert not r['cases'][0]['full_period_profit_interpretable']


def test_duplicate_calendar_or_ledger_date_rejected():
    rows=[dict(date='2026-10-12',open='09:30',close='16:00')]*2
    with pytest.raises(ValueError): calendar_dates(rows,'2026-10-12','2026-10-13')
    with pytest.raises(ValueError): inspect(source(['2026-10-12']*2),calendar())


def test_extra_non_calendar_day_not_silently_dropped():
    r=inspect(source(['2026-10-12','2026-10-13','2026-10-14']),calendar())
    assert r['cases'][0]['non_calendar_ledger_dates']==['2026-10-14']
    assert not r['all_observed_spans_cover_calendar']


def test_short_session_incompatible_with_horizon_rejected():
    c=calendar();c['2026-10-13']['close']='11:00'
    r=inspect(source(['2026-10-12','2026-10-13']),c)
    assert r['cases'][0]['unsupported_session_windows']==['2026-10-13']
