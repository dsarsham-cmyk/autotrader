from copy import deepcopy
import numpy as np
from causal_opening_inventory import opening_rows,inspect
from tests.test_iex_bar_predictive_research import fixture


def test_future_close_changes_or_missing_cannot_select_current_signal():
    dates,observations,complete=fixture();before,_=opening_rows(observations)
    for symbol in observations:
        regular=observations[symbol][dates[-1]]
        observations[symbol][dates[-1]]=regular.loc[regular.minute<600].copy()
    after,_=opening_rows(observations)
    assert before==after


def test_outcome_absence_does_not_change_signal_or_causal_market_context():
    dates,observations,complete=fixture();before,_=opening_rows(observations)
    del complete[dates[-1]]['B']
    result=inspect(observations,complete);after,_=opening_rows(observations)
    assert before==after and result['full_outcome_missing_rows']==1
    assert result['missing_outcomes'][0]['status']=='unknown_outcome_not_no_trade_or_win'
    assert not result['performance_screen_pass']


def test_full_day_filter_changes_cross_section_when_missing_stock_differs():
    dates,observations,complete=fixture()
    regular=observations['B'][dates[-1]]
    regular.loc[regular.minute<600,['open','high','low','close']]=[100,111,99,110]
    del complete[dates[-1]]['B']
    report=inspect(observations,complete)
    assert report['cross_section_changed_dates']==1
    change=report['cross_section_changes'][0]
    assert change['causal_mean_return']>change['complete_only_mean_return']


def test_incomplete_opening_is_rejected_even_if_future_outcome_exists():
    dates,observations,complete=fixture()
    regular=observations['B'][dates[-1]]
    observations['B'][dates[-1]]=regular.loc[regular.minute!=580].copy()
    rows,reasons=opening_rows(observations)
    assert 'B' not in rows[dates[-1]] and reasons[(dates[-1],'B')]=='incomplete_opening'


def test_future_missing_close_affects_only_later_history():
    dates,observations,complete=fixture();before,_=opening_rows(observations)
    prior_day=dates[-2];regular=observations['B'][prior_day]
    regular.loc[regular.minute>=955,'close']=100.5
    regular.loc[regular.minute>=955,'high']=101
    after,_=opening_rows(observations)
    assert before[prior_day]==after[prior_day]
    assert before[dates[-1]]['B']!=after[dates[-1]]['B']


def test_no_current_future_close_can_replace_required_past_history():
    dates,observations,complete=fixture()
    for regular in observations['A'].values():
        regular.loc[regular.minute>=955,'volume']=2000
    limited={'A':dict(list(observations['A'].items())[:21])}
    rows,_=opening_rows(limited)
    assert not rows


def test_trade_window_coverage_is_metadata_not_candidate_selection():
    dates,observations,complete=fixture();date=dates[-1]
    regular=observations['B'][date]
    # Add actual modeled window observations; there are still later gaps.
    import pandas as pd
    window=pd.DataFrame(dict(symbol='B',timestamp='fixture',open=100.,high=101.,
        low=99.,close=100.,volume=1000.,date=date,minute=list(range(616,678))))
    observations['B'][date]=pd.concat([regular,window],ignore_index=True).sort_values('minute')
    del complete[date]['B'];before,_=opening_rows(observations)
    report=inspect(observations,complete)
    assert report['excluded_rows_with_complete_fixed_trade_window']==1
    observations['B'][date]=observations['B'][date].loc[lambda a:a.minute!=640]
    after,_=opening_rows(observations);missing=inspect(observations,complete)
    assert before==after and missing['excluded_rows_with_complete_fixed_trade_window']==0
