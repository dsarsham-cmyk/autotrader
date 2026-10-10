import numpy as np
import pytest
import reward_policy_research as research
from reward_policy_simulator import path,portfolio,economics
from tighter_stop_simulator import path as old_path,portfolio as old_portfolio
from prospective_series_audit import accounting_metrics


def bars(): return np.tile([100.,100.2,99.8,100.,1000.],(390,1))


@pytest.mark.parametrize('target',[.002,.02,True,float('nan')])
def test_only_predeclared_reward_policies_allowed(target):
    with pytest.raises(ValueError): path(bars(),100,target)


def test_reference_path_and_accounting_unchanged():
    a=bars();a[60,1]=101
    current=path(a,100,.004);current.pop('target_fraction')
    assert current==old_path(a,100,.01)
    rows=[dict(date=d,symbol='A',probability=.8,signal_price=100) for d in ['a','b']]
    data={'a':{'A':(a,{})},'b':{'A':(bars(),{})}}
    before=old_portfolio(rows,data,.01,.65);after=portfolio(rows,data,.004,.65)
    for k in ['daily','profit_usd','active_days','active_day_win_rate_pct','worst_day_usd']:
        assert before[k]==after[k]


def test_larger_target_can_change_label_without_changing_stop_or_time_cap():
    a=bars();a[50,1]=100.6;a[60:107]=[99.5,99.7,99.3,99.5,1000]
    small=path(a,100,.004);large=path(a,100,.012)
    assert small['label']==1 and large['label']==0
    assert small['stop']==large['stop'] and large['exit_minute']==106
    a[120,1]=102
    assert path(a,100,.012)==large  # post-horizon rally is not credited


def test_same_bar_stop_first_and_gap_not_capped():
    a=bars();a[50]=[98,102,97,98,1000]
    result=path(a,100,.012)
    assert result['reason']=='stop' and result['exit']==pytest.approx(98*.999)
    assert result['exit']<result['stop']*.999


def test_profit_target_does_not_change_quantity_or_budget_caps():
    rows=[dict(date='a',symbol=s,probability=.9,signal_price=100) for s in 'ABCD']
    data={'a':{s:(bars(),{}) for s in 'ABCD'}}
    small=portfolio(rows,data,.004,.65);large=portfolio(rows,data,.012,.65)
    assert [t['quantity'] for t in small['trades']]==[t['quantity'] for t in large['trades']]
    metrics=accounting_metrics(large,rows)
    assert all(metrics[k] for k in ['category_budget_pass','stock_budget_pass','max_positions_pass','planned_risk_pass'])
    assert not large['orders'] and not large['production_approved'] and not large['independent_validation_pass']


def test_higher_target_improves_algebra_not_prediction():
    assert economics(.004)['exact_trade_breakeven_pct']>85
    assert economics(.012)['exact_trade_breakeven_pct']<55
    assert economics(.004,20)['exact_trade_breakeven_pct'] is None


@pytest.mark.parametrize('kind',['logistic','mlp','quantum_fidelity'])
def test_models_refit_policy_specific_past_labels_and_keep_unknown_test_fills(monkeypatch,kind):
    rows=[dict(date=f'{i:04d}',symbol='A',features=[1],signal_price=100) for i in range(261)]
    data={r['date']:{'A':(bars(),{})} for r in rows}
    a=data['0001']['A'][0];a[50,1]=100.6;a[60:107]=[99.5,99.7,99.3,99.5,1000]
    data['0260']['A'][0][46]=[102,103,101,102,1000]
    seen=[]
    def fit(train,cal,test,kind,labels):
        assert max(r['date'] for r in train)<min(r['date'] for r in cal)
        assert max(r['date'] for r in cal)<min(r['date'] for r in test)
        seen.append(labels[('0001','A')])
        return np.full(len(test),.7)
    monkeypatch.setattr(research,'fit_predict',fit)
    monkeypatch.setattr(research,'predict_kernel',lambda tr,ca,te,la,ki:fit(tr,ca,te,ki,la))
    monkeypatch.setattr(research,'predict_neural',lambda tr,ca,te,la:(fit(tr,ca,te,'mlp',la),{}))
    before,_=research.walk(rows,data,.004,kind);after,_=research.walk(rows,data,.012,kind)
    assert len(before)==len(after)==21 and seen==[1,1,0,0]


def test_future_test_outcome_cannot_change_any_fitting_labels_used(monkeypatch):
    rows=[dict(date=f'{i:04d}',symbol='A',features=[1],signal_price=100) for i in range(261)]
    data={r['date']:{'A':(bars(),{})} for r in rows}
    def fit(train,cal,test,kind,labels):
        return np.full(len(test),np.mean([labels[(r['date'],r['symbol'])] for r in train+cal]))
    monkeypatch.setattr(research,'fit_predict',fit)
    before,_=research.walk(rows,data,.008,'logistic')
    data['0260']['A'][0][60,1]=102
    after,_=research.walk(rows,data,.008,'logistic')
    assert before==after
