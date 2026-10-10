import numpy as np
import pytest
import profit_lock_research as research
from profit_lock_simulator import path,portfolio
from causal_sparse_simulator import path as old_path,portfolio as old_portfolio
from prospective_series_audit import accounting_metrics


def bars(): return {i:np.array([100.,100.2,99.8,100.,1000.]) for i in range(390)}


def activated():
    a=bars();a[46]=np.array([100.,100.35,99.9,100.3,1000.])
    a[47]=np.array([100.3,100.35,100.25,100.3,1000.])
    a[48]=np.array([100.25,100.3,100.2,100.25,1000.])
    return a


@pytest.mark.parametrize('delay',[16,17])
def test_disabled_policy_path_and_portfolio_exact_reference(delay):
    a=bars();a[60][1]=101.
    assert path(a,100,delay=delay)==old_path(a,100,delay=delay)
    rows=[dict(date='a',symbol=s,signal_price=100.,probability=.8) for s in 'ABCD']
    market={'a':{s:a for s in 'ABCD'}}
    before=old_portfolio(rows,market,.65,delay=delay);after=portfolio(rows,market,.65,delay=delay)
    for k in ['daily','trades','profit_usd','unknown_selections']: assert before[k]==after[k]


def test_profit_lock_never_applies_to_same_bar_low():
    o=path(activated(),100,protect=True)
    assert o['reason']=='profit_lock' and o['exit_minute']==48 and o['label']==1
    assert o['protection_updates'][0]['effective_minute']==47
    assert o['exit']/o['entry']-1==pytest.approx(.0002)
    assert o['stop']==99. # Planned-risk sizing remains tied to original protection.


def test_gap_can_destroy_protected_profit_not_fabricated_fill():
    a=activated();a[47]=np.array([98.,99.,97.,98.,1000.])
    o=path(a,100,protect=True)
    assert o['reason']=='profit_lock' and o['exit']==pytest.approx(98*.999) and o['label']==0


def test_original_stop_wins_before_later_same_bar_activation():
    a=activated();a[46][2]=98.
    o=path(a,100,protect=True)
    assert o['reason']=='stop' and o['exit_minute']==46 and o['protection_updates']==[]


def test_invalid_close_for_stop_request_and_infeasible_cost_cannot_activate():
    a=bars();a[46]=activated()[46].copy();a[46][3]=100.
    assert path(a,100,protect=True)['protection_updates']==[]
    a=activated();a[46][0]=99.9
    assert path(a,100,cost_bps=20,protect=True)['protection_updates']==[]


def test_missing_next_minute_not_replaced_with_protected_price():
    a=activated();del a[47]
    assert path(a,100,protect=True) is None


def test_same_initial_risk_and_caps_after_profit_lock():
    a=activated();rows=[dict(date='a',symbol=s,signal_price=100.,probability=.8) for s in 'ABCD']
    r=portfolio(rows,{'a':{s:a for s in 'ABCD'}},.65,protect=True)
    metrics=accounting_metrics(r,rows)
    assert len(r['trades'])==3 and all(metrics[k] for k in ['stock_budget_pass','category_budget_pass','max_positions_pass','planned_risk_pass'])


def test_training_uses_own_past_protected_labels_and_keeps_unknown_future(monkeypatch):
    rows=[dict(date=f'{i:04d}',symbol='A',signal_price=100.,features=[1.]) for i in range(261)]
    market={r['date']:{'A':activated()} for r in rows};market['0260']={'A':{}}
    def fit(train,cal,test,model,labels):
        assert labels[('0001','A')]==1 and ('0260','A') not in labels
        assert max(r['date'] for r in train)<min(r['date'] for r in cal)<min(r['date'] for r in test)
        return np.full(len(test),.7)
    monkeypatch.setattr(research,'fit_predict',fit)
    forecasts,_=research.walk(rows,market,'logistic',True)
    assert any(r['date']=='0260' for r in forecasts)
