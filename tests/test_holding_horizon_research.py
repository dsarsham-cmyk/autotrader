import numpy as np
import pytest
import holding_horizon_research as research
from holding_horizon_simulator import path,portfolio
from causal_sparse_simulator import path as old_path,portfolio as old_portfolio
from prospective_series_audit import accounting_metrics


def bars(): return {i:np.array([100.,100.2,99.8,100.,1000.]) for i in range(390)}


@pytest.mark.parametrize('delay',[16,17])
@pytest.mark.parametrize('cost',[10,20])
def test_one_hour_path_and_portfolio_exactly_match_reference(delay,cost):
    a=bars();a[60][1]=101.
    assert path(a,100,cost,delay,60)==old_path(a,100,cost,delay)
    rows=[dict(date='a',symbol=s,signal_price=100.,probability=.8) for s in 'ABCD']
    market={'a':{s:a for s in 'ABCD'}}
    before=old_portfolio(rows,market,.65,cost,delay);after=portfolio(rows,market,.65,cost,delay,60)
    for key in ['daily','trades','profit_usd','active_days','unknown_selections']:
        assert before[key]==after[key]


def test_second_hour_target_is_observed_not_backdated_to_first_hour():
    a=bars();a[140][1]=101.
    short=path(a,100,horizon=60);long=path(a,100,horizon=120)
    assert short['reason']=='horizon' and short['exit_minute']==106 and short['label']==0
    assert long['reason']=='target' and long['exit_minute']==140 and long['label']==1


def test_missing_second_hour_stops_only_long_horizon_ledger():
    a=bars();del a[120]
    rows=[dict(date='a',symbol='A',signal_price=100.,probability=.8)]
    short=portfolio(rows,{'a':{'A':a}},.65,horizon=60)
    long=portfolio(rows,{'a':{'A':a}},.65,horizon=120)
    assert short['full_period_coverage_complete']
    assert long['profit_usd'] is None and not long['target_screen_pass'] and long['daily']==[]


def test_long_horizon_stop_and_budget_are_not_relaxed():
    a=bars();a[130]=np.array([98.,100.,97.,98.,1000.])
    o=path(a,100,horizon=120)
    assert o['reason']=='stop' and o['exit']==pytest.approx(98*.999) and o['stop']==99.
    rows=[dict(date='a',symbol=s,signal_price=100.,probability=.8) for s in 'ABCD']
    r=portfolio(rows,{'a':{s:a for s in 'ABCD'}},.65,horizon=120)
    metrics=accounting_metrics(r,rows)
    assert all(metrics[k] for k in ['stock_budget_pass','category_budget_pass','max_positions_pass','planned_risk_pass'])
    assert len(r['trades'])==3 and all(t['exit_minute']==130 for t in r['trades'])


def test_unfilled_and_early_exit_require_no_later_observations():
    assert not path({46:np.array([102.,103.,101.,102.,1000.])},100,horizon=120)['filled']
    a={46:np.array([100.,100.5,99.8,100.,1000.])}
    assert path(a,100,horizon=120)['exit_minute']==46


def test_past_labels_are_own_horizon_and_future_unknown_candidates_retained(monkeypatch):
    rows=[dict(date=f'{i:04d}',symbol='A',signal_price=100.,features=[1.]) for i in range(261)]
    a=bars();a[140][1]=101.
    market={r['date']:{'A':a} for r in rows};market['0260']={'A':{}}
    def fit(train,cal,test,model,labels):
        assert labels[('0001','A')]==1
        assert max(r['date'] for r in train)<min(r['date'] for r in cal)
        assert max(r['date'] for r in cal)<min(r['date'] for r in test)
        assert ('0260','A') not in labels
        return np.full(len(test),.7)
    monkeypatch.setattr(research,'fit_predict',fit)
    forecasts,_=research.walk(rows,market,'logistic',120)
    assert any(r['date']=='0260' for r in forecasts)


def test_unplanned_horizon_rejected():
    with pytest.raises(ValueError): path(bars(),100,horizon=390)
