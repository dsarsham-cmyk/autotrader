import numpy as np
import pytest
from tighter_stop_simulator import path,portfolio,theoretical_economics
from predictive_portfolio_research import path_outcome,portfolio as reference


def bars(): return np.tile([100.,100.2,99.8,100.,1000.],(390,1)).astype(float)


@pytest.mark.parametrize('stop',[.02,0,-.01,float('nan'),True])
def test_stop_cannot_be_widened_or_invalid(stop):
    with pytest.raises(ValueError): path(bars(),100,stop)


def test_reference_stop_path_matches_frozen_code():
    a=bars();a[60,1]=101
    assert path(a,100,.01)==path_outcome(a,100,30,'target_60',10,16)


def test_one_percent_portfolio_matches_reference_accounting():
    rows=[dict(date=d,symbol='A',signal_price=100,probability=.8) for d in ['a','b']]
    data={d:{'A':(bars(),{})} for d in ['a','b']};data['a']['A'][0][60,1]=101
    expected=reference(rows,data,30,'target_60',.65,10,16);actual=portfolio(rows,data,.01,.65)
    for key in ['profit_usd','active_days','active_day_win_rate_pct','win_rate_interval','worst_day_usd']:
        assert actual[key]==expected[key]
    for before,after in zip(expected['daily'],actual['daily']):
        assert all(before[key]==after[key] for key in before)
    for before,after in zip(expected['trades'],actual['trades']):
        assert all(before[key]==after[key] for key in before)


def test_tighter_stop_changes_label_before_later_target():
    a=bars();a[50,2]=99.6;a[60,1]=101
    assert path(a,100,.01)['label']==1
    tightened=path(a,100,.0025)
    assert tightened['label']==0 and tightened['exit_minute']==50 and tightened['reason']=='stop'


def test_same_bar_stop_target_and_gap_conservative():
    a=bars();a[50]=[98,101,97,98,1000]
    outcome=path(a,100,.0025)
    assert outcome['reason']=='stop' and outcome['exit']==pytest.approx(98*.999)
    assert outcome['exit']<outcome['stop']*.999  # gap exceeds planned loss


def test_before_entry_path_cannot_trigger_a_stop():
    a=bars();a[45]=[98,101,97,98,1000];a[60,1]=101
    assert path(a,100,.0025)['reason']=='target'


def test_new_policy_keeps_caps_and_actual_tighter_risk():
    rows=[dict(date='a',symbol=s,signal_price=100,probability=.9) for s in 'ABCD']
    data={'a':{s:(bars(),{}) for s in 'ABCD'}}
    result=portfolio(rows,data,.0025,.65)
    assert len(result['trades'])==3 and result['daily'][0]['committed_usd']<=3000
    assert result['actual_tighter_stop_planned_risk_pass']
    assert all(t['reserved_usd']<=1000 for t in result['trades'])
    assert not result['orders'] and not result['production_approved'] and not result['independent_validation_pass']


def test_no_trade_not_win_and_duplicate_stock_rejected():
    rows=[dict(date='a',symbol='A',signal_price=100,probability=.1)];data={'a':{'A':(bars(),{})}}
    result=portfolio(rows,data,.0025,.65)
    assert result['no_trade_days']==1 and result['active_day_win_rate_pct'] is None
    assert not result['target_screen_pass']
    with pytest.raises(ValueError,match='Duplicate'): portfolio(rows+rows,data,.0025,.65)


def test_trade_breakeven_improves_but_not_a_day_forecast():
    old=theoretical_economics(.01);tight=theoretical_economics(.0025)
    assert old['exact_target_stop_trade_breakeven_win_rate_pct']>85
    assert tight['exact_target_stop_trade_breakeven_win_rate_pct']<70
    assert theoretical_economics(.0025,20)['exact_target_stop_trade_breakeven_win_rate_pct'] is None


def test_gap_can_overshoot_daily_trigger_despite_planned_risk_cap():
    rows=[dict(date='a',symbol=s,signal_price=100,probability=.9) for s in 'ABC']
    data={'a':{s:(bars(),{}) for s in 'ABC'}}
    for a,_ in data['a'].values(): a[60]=[50,51,49,50,1000]
    result=portfolio(rows,data,.0025,.65)
    assert result['actual_tighter_stop_planned_risk_pass']
    assert result['daily_trigger_gap_overshoot_days']==1
    assert result['profit_usd']<-1000  # do not falsely cap gap loss at stop/guard
