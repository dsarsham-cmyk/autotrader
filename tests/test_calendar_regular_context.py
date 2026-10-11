from copy import deepcopy
import pandas as pd
import pytest
from calendar_regular_context import calendar_lookup,calendar_opening_rows,inspect
from split_context_audit import normalized_opening_rows
from tests.test_iex_bar_predictive_research import fixture
from tests.test_split_context_audit import split_fixture


def schedule(dates):
    return calendar_lookup([dict(date=d,open='09:30',close='16:00') for d in dates])


def test_normal_calendar_exact_with_splits():
    dates,observations,event=split_fixture()
    assert calendar_opening_rows(observations,[event],schedule(dates)) == normalized_opening_rows(observations,[event])


def half_fixture():
    dates,observations,_=fixture()
    cal=schedule(dates)
    cal[dates[-2]]['close_minute']=780
    for symbol in observations:
        frame=observations[symbol][dates[-2]]
        closing=frame.loc[frame.minute>=955].copy()
        closing['minute']-=180
        observations[symbol][dates[-2]]=pd.concat([frame,closing],ignore_index=True).sort_values('minute')
    return dates,observations,cal


def test_after_hours_never_change_next_opening():
    dates,observations,cal=half_fixture()
    before=calendar_opening_rows(observations,[],cal)
    for symbol in observations:
        frame=observations[symbol][dates[-2]]
        frame.loc[frame.minute>=780,['open','high','low','close']]*=2
    assert before==calendar_opening_rows(observations,[],cal)
    old,_,_=normalized_opening_rows(observations,[])
    assert old[dates[-1]]!=before[0][dates[-1]]
    assert before[0][dates[-1]]['A']['features'][13]==0


def test_current_future_close_cannot_change_candidate_or_mutate_inputs():
    dates,observations,cal=half_fixture()
    saved=deepcopy(observations)
    before=calendar_opening_rows(observations,[],cal)
    for s in observations:
        assert all(observations[s][d].equals(saved[s][d]) for d in dates)
        observations[s][dates[-1]]=observations[s][dates[-1]].loc[lambda r:r.minute<600]
    assert before==calendar_opening_rows(observations,[],cal)


def test_audit_reports_exclusion_not_profit():
    _,observations,cal=half_fixture()
    report=inspect(observations,[],cal)
    assert report['excluded_after_close_bars']==10
    assert report['normal_close_control_exact']
    assert all(report[k] is False for k in ['orders','performance_screen_pass','independent_validation_pass','economic_evaluation_performed'])


def test_missing_or_duplicate_calendar_fails():
    dates,observations,_=fixture()
    cal=schedule(dates)
    del cal[dates[-2]]
    with pytest.raises(ValueError,match='absent'): calendar_opening_rows(observations,[],cal)
    rows=[dict(date=dates[0],open='09:30',close='13:00')]*2
    with pytest.raises(ValueError,match='Duplicate'): calendar_lookup(rows)
    with pytest.raises(ValueError): calendar_lookup([dict(date=dates[0],open='09:30',close='11:00')])


def test_regular_half_day_close_retained_without_after_hours():
    dates,observations,cal=half_fixture()
    expected=calendar_opening_rows(observations,[],cal)
    for s in observations:
        observations[s][dates[-2]]=observations[s][dates[-2]].loc[lambda r:r.minute<780]
    assert expected==calendar_opening_rows(observations,[],cal)
    assert dates[-1] in expected[0]


def test_future_split_never_changes_calendar_inputs():
    dates,observations,cal=half_fixture()
    before=calendar_opening_rows(observations,[],cal)
    future=dict(symbol='A',ex_date='2027-01-01',ratio=10)
    assert before==calendar_opening_rows(observations,[future],cal)
