import numpy as np
import pytest
from predictive_portfolio_research import build, partition, path_outcome, portfolio


def prices():
    return np.tile([100.,100.2,99.8,100.,1000.],(390,1)).astype(float)


def universe():
    return {f'{i:04d}':{'A':(prices(),dict(prior_dollars=3e7,relative_volume=1))}
            for i in range(25)}


def test_future_day_path_does_not_change_same_day_features():
    data=universe()
    original=build(data,15)
    data['0024']['A'][0][16:,3]=110
    altered=build(data,15)
    assert original[-1]['features']==altered[-1]['features']


def test_entire_date_stays_in_one_split():
    records=[{'date':'a','symbol':'A'},{'date':'a','symbol':'B'},
             {'date':'b','symbol':'A'}]
    assert len(partition(records,['a']))==2
    assert len(partition(records,['b']))==1


def test_stop_gap_and_higher_costs():
    a=prices();a[30]=[95,96,94,95,1000]
    low=path_outcome(a,100,15,'session',10)
    high=path_outcome(a,100,15,'session',20)
    assert low['reason']=='stop' and low['exit']==pytest.approx(95*.999)
    assert high['exit']<low['exit'] and high['entry']>low['entry']


def test_abstention_is_not_a_win():
    rows=[dict(date='a',symbol='A',signal_price=100,probability=.5)]
    data={'a':{'A':(prices(),{})}}
    result=portfolio(rows,data,15,'session',.9)
    assert result['active_days']==0 and result['no_trade_days']==1
    assert result['active_day_win_rate_pct'] is None
    assert not result['independent_validation_pass']


def test_allocation_cap_and_limit_rejection():
    rows=[dict(date='a',symbol=s,signal_price=100,probability=.95) for s in 'ABCD']
    data={'a':{s:(prices(),{}) for s in 'ABCD'}}
    result=portfolio(rows,data,15,'session',.9)
    assert len(result['trades'])<=3
    assert result['daily'][0]['committed_usd']<=3000
    data['a']['A'][0][16,0]=110
    result=portfolio(rows[:1],data,15,'session',.9)
    assert result['active_days']==0


def test_target_and_stop_same_bar_uses_stop_not_optimistic_order():
    a=prices();a[20]=[100,101,98,100,1000]
    result=path_outcome(a,100,15,'target_60')
    assert result['reason']=='stop'


def test_target_is_fixed_before_later_bars():
    a=prices();a[20,1]=101
    result=path_outcome(a,100,15,'target_session')
    assert result['reason']=='target'
    assert result['exit']==pytest.approx(100*1.004*.999)
