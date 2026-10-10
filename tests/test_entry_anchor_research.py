import numpy as np
import pytest
from entry_anchor_research import anchor_rows
from reward_policy_simulator import path,portfolio
from prospective_series_audit import accounting_metrics


def fixture():
    a=np.tile([100.,100.2,99.8,100.,1000.],(390,1));a[29]=[102,102.2,101.8,102,1000]
    return [dict(date='d',symbol='A',features=[1],signal_price=102,probability=.8)],{'d':{'A':(a,{})}}


def test_anchor_uses_only_known_first30_bars():
    rows,data=fixture();before=anchor_rows(rows,data,'opening_vwap_pullback')
    data['d']['A'][0][30:]=[200,210,190,200,900000]
    assert anchor_rows(rows,data,'opening_vwap_pullback')==before
    assert rows[0]['signal_price']==102


def test_vwap_policy_never_increases_close_limit():
    rows,data=fixture()
    assert anchor_rows(rows,data,'opening_vwap_pullback')[0]['signal_price']<102
    data['d']['A'][0][29]=[98,98.2,97.8,98,1000]
    assert anchor_rows(rows,data,'opening_vwap_pullback')[0]['signal_price']==98


def test_stricter_anchor_can_abstain_without_future_dip_fill():
    rows,data=fixture();a=data['d']['A'][0];a[46]=[101,101.2,100.8,101,1000]
    close=anchor_rows(rows,data,'opening_close')[0]
    dip=anchor_rows(rows,data,'opening_vwap_pullback')[0]
    assert path(a,close['signal_price'],.004)['filled']
    assert not path(a,dip['signal_price'],.004)['filled']
    a[47]=[99,99.2,98.8,99,1000]
    assert not path(a,dip['signal_price'],.004)['filled']


def test_policy_keeps_existing_risk_caps():
    rows,data=fixture();inputs=anchor_rows(rows,data,'opening_vwap_pullback')
    r=portfolio(inputs,data,.004,.65)
    metrics=accounting_metrics(r,inputs)
    assert all(metrics[k] for k in ['category_budget_pass','stock_budget_pass','max_positions_pass','planned_risk_pass'])
    assert not r['orders'] and not r['independent_validation_pass']


def test_unknown_policy_rejected():
    rows,data=fixture()
    with pytest.raises(ValueError): anchor_rows(rows,data,'best_hindsight')


@pytest.mark.parametrize('kind',['logistic','boosted'])
def test_each_policy_refits_own_past_fill_pool_without_filtering_test(monkeypatch,kind):
    import reward_policy_research as research
    rows=[];data={}
    for i in range(261):
        source,stocks=fixture();row=dict(source[0],date=f'{i:04d}')
        rows.append(row);data[row['date']]=stocks['d']
    # One past sample fills close policy but not the stricter VWAP policy.
    data['0001']['A'][0][46]=[101,101.2,100.8,101,1000]
    # Latest test sample does not fill either policy; it MUST still be forecast.
    data['0260']['A'][0][46]=[104,104.2,103.8,104,1000]
    seen=[]
    def fit(train,cal,test,model,labels):
        assert max(r['date'] for r in train)<min(r['date'] for r in cal)
        assert max(r['date'] for r in cal)<min(r['date'] for r in test)
        if any(r['date']=='0260' for r in test):
            assert next(r for r in test if r['date']=='0260')['symbol']=='A'
        seen.append(len(train));return np.full(len(test),.7)
    monkeypatch.setattr(research,'fit_predict',fit)
    first,_=research.walk(anchor_rows(rows,data,'opening_close'),data,.004,kind)
    close_counts=list(seen);seen.clear()
    second,_=research.walk(anchor_rows(rows,data,'opening_vwap_pullback'),data,.004,kind)
    assert all(b==a-1 for a,b in zip(close_counts,seen))
    assert any(r['date']=='0260' for r in first) and any(r['date']=='0260' for r in second)
