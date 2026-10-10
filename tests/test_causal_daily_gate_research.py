import copy
import pytest
from causal_daily_gate_research import records,gated
from daily_meta_research import fit_meta


def forecasts():
    return [dict(date=d,symbol='A',features=[1.,2.],signal_price=100.,probability=.8) for d in ['a','b','c']]


def test_unknown_later_outcomes_keep_features_but_cannot_train():
    rows=records(forecasts(),dict(daily=[dict(date='a',active=True,pnl=-1.)]))
    assert len(rows)==3 and rows[0]['label']==0 and rows[0]['outcome_known']
    assert rows[1]['label'] is None and not rows[1]['outcome_known'] and not rows[1]['base_active']
    with pytest.raises(ValueError,match='Insufficient'): fit_meta(rows,rows,rows,'logistic')


def test_day_features_do_not_depend_on_profit_or_future_label():
    first=records(forecasts(),dict(daily=[dict(date='a',active=True,pnl=-1.)]))
    second=records(forecasts(),dict(daily=[dict(date='a',active=True,pnl=999.)]))
    assert [r['features'] for r in first]==[r['features'] for r in second]


def test_gate_retains_all_test_dates_and_explicit_original_probability():
    original=forecasts();before=copy.deepcopy(original)
    result=gated(original,{'b':None,'c':.95},.9)
    assert [r['date'] for r in result]==['b','c']
    assert result[0]['probability']==0. and result[0]['stock_probability']==.8
    assert result[1]['probability']==.8 and result[1]['day_probability']==.95
    assert original==before


def test_known_no_trade_day_is_not_winning_label():
    rows=records(forecasts(),dict(daily=[dict(date='a',active=False,pnl=0.)]))
    assert rows[0]['label']==0 and not rows[0]['base_active'] and rows[0]['outcome_known']
