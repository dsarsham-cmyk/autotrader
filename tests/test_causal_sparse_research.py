import numpy as np
import pytest
import causal_sparse_research as research
from causal_sparse_simulator import path,portfolio
from tighter_stop_simulator import path as old_path,portfolio as old_portfolio
from prospective_series_audit import accounting_metrics


def bars(): return np.tile([100.,100.2,99.8,100.,1000.],(390,1))
def mapping(a): return {i:row.copy() for i,row in enumerate(a)}


@pytest.mark.parametrize('delay',[16,17])
def test_complete_path_matches_reference_and_irrelevant_future_absence(delay):
    a=bars();a[60,1]=101
    expected=old_path(a,100,.01,10,delay)
    assert path(mapping(a),100,10,delay)==expected
    assert path({i:a[i] for i in range(30+delay,61)},100,10,delay)==expected


def test_unknown_required_price_is_not_a_win_or_fabricated_fill():
    market=mapping(bars());del market[50]
    assert path(market,100) is None
    del market[46]
    assert path(market,100) is None


def test_known_unfilled_order_needs_no_later_outcome():
    o=path({46:np.array([102,103,101,102,1000])},100)
    assert not o['filled'] and 'label' not in o


def test_stop_before_missing_later_price_is_known_and_gap_not_capped():
    market={46:np.array([100,100.2,99.8,100,1000]),47:np.array([98,102,97,98,1000])}
    o=path(market,100)
    assert o['reason']=='stop' and o['exit']==pytest.approx(98*.999)


def test_complete_portfolio_matches_existing_limits_and_accounting():
    a=bars();a[60,1]=101
    rows=[dict(date=d,symbol=s,signal_price=100,probability=.8) for d in ['a','b'] for s in 'ABCD']
    full={d:{s:(a,{}) for s in 'ABCD'} for d in ['a','b']}
    sparse={d:{s:mapping(a) for s in 'ABCD'} for d in ['a','b']}
    before=old_portfolio(rows,full,.01,.65);after=portfolio(rows,sparse,.65)
    for k in ['daily','trades','profit_usd','active_days','active_day_win_rate_pct']:
        assert before[k]==after[k]
    assert all(accounting_metrics(after,rows)[k] for k in ['stock_budget_pass','category_budget_pass','max_positions_pass','planned_risk_pass'])


def test_unknown_selected_position_stops_entire_ledger_without_substitution():
    a=bars();a[60,1]=101
    rows=[dict(date=d,symbol=s,signal_price=100,probability=.9 if s=='A' else .8) for d in ['a','b','c'] for s in 'ABCD']
    market={d:{s:mapping(a) for s in 'ABCD'} for d in ['a','b','c']};del market['b']['A'][46]
    result=portfolio(rows,market,.65)
    assert result['profit_usd'] is None and result['active_day_win_rate_pct'] is None
    assert result['known_prefix_sessions']==1 and result['unknown_selections'][0]['date']=='b'
    assert all(t['date']=='a' and t['symbol']!='D' for t in result['trades'])
    assert not result['target_screen_pass'] and not result['full_period_coverage_complete']


def test_unknown_unselected_stock_cannot_reject_day():
    rows=[dict(date='a',symbol=s,signal_price=100,probability=.9 if s=='A' else .1) for s in 'AB']
    r=portfolio(rows,{'a':{'A':mapping(bars()),'B':{}}},.65)
    assert r['full_period_coverage_complete'] and not r['unknown_selections']


def test_loss_guard_and_gap_overshoot_match_full_data_reference():
    rows=[dict(date='a',symbol=s,signal_price=100,probability=.8) for s in 'ABC']
    arrays={s:bars() for s in 'ABC'}
    for s in 'AB': arrays[s][60]=[20,21,19,20,1000]
    full={'a':{s:(a,{}) for s,a in arrays.items()}}
    sparse={'a':{s:mapping(a) for s,a in arrays.items()}}
    before=old_portfolio(rows,full,.01,.65);after=portfolio(rows,sparse,.65)
    assert before['daily']==after['daily'] and before['trades']==after['trades']
    assert after['daily'][0]['guard'] and after['daily'][0]['realized_loss_exceeded_daily_trigger']
    assert any(t['reason']=='account_guard' for t in after['trades'])


def test_invalid_observed_required_bar_is_not_treated_as_unknown():
    market=mapping(bars());market[46][1]=90
    with pytest.raises(ValueError,match='OHLC'): path(market,100)


@pytest.mark.parametrize('kind',['logistic','boosted'])
def test_past_unknown_labels_excluded_but_future_unknown_candidates_forecast(monkeypatch,kind):
    rows=[dict(date=f'{i:04d}',symbol='A',signal_price=100,features=[1]) for i in range(261)]
    market={r['date']:{'A':mapping(bars())} for r in rows}
    del market['0001']['A'][46];del market['0260']['A'][46]
    def fit(train,cal,test,model,labels):
        assert all(r['date']!='0001' for r in train)
        assert max(r['date'] for r in train)<min(r['date'] for r in cal)
        assert max(r['date'] for r in cal)<min(r['date'] for r in test)
        assert ('0260','A') not in labels
        return np.full(len(test),.7)
    monkeypatch.setattr(research,'fit_predict',fit)
    forecasts,_=research.walk(rows,market,kind)
    assert any(r['date']=='0260' for r in forecasts)
