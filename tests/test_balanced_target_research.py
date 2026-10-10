import numpy as np
import pytest
import balanced_target_research as research
from balanced_target_simulator import path,portfolio
from causal_sparse_simulator import path as original_path,portfolio as original_portfolio


def bars():
    return {k:np.asarray([100.,100.5,99.9,100.,1000.]) for k in range(46,107)}


def test_control_paths_and_portfolios_exact():
    prices=bars()
    assert path(prices,100.)==original_path(prices,100.)
    market={'d':{'AAPL':prices}};forecasts=[dict(date='d',symbol='AAPL',probability=.9,signal_price=100.)]
    result=portfolio(forecasts,market,.65);expected=original_portfolio(forecasts,market,.65)
    assert {k:v for k,v in result.items() if k!='target_fraction'}==expected


def test_target_changes_exit_not_stop_or_risk_and_missing_is_unknown():
    prices=bars();old=path(prices,100.);new=path(prices,100.,target_fraction=.01)
    assert old['reason']=='target' and new['reason']=='horizon'
    assert all(old[k]==new[k] for k in ('stop','entry','limit','cost','entry_minute'))
    del prices[60]
    assert path(prices,100.) is not None
    assert path(prices,100.,target_fraction=.01) is None
    result=portfolio([dict(date='d',symbol='AAPL',probability=.9,signal_price=100.)],{'d':{'AAPL':prices}},.65,target_fraction=.01)
    assert result['profit_usd'] is None and not result['full_period_coverage_complete'] and not result['target_screen_pass']


def test_same_bar_stop_first_gap_not_artificially_capped():
    prices=bars();prices[46]=np.asarray([100.,102.,98.,100.,1000.])
    result=path(prices,100.,target_fraction=.01)
    assert result['reason']=='stop' and result['exit']==pytest.approx(99*.999)
    prices=bars();prices[47]=np.asarray([97.,98.,96.,97.,1000.])
    result=path(prices,100.,target_fraction=.01)
    assert result['reason']=='stop' and result['exit']==pytest.approx(97*.999)
    assert path({},100.,target_fraction=.01) is None
    for target in (.02,.008,True):
        with pytest.raises(ValueError): path(bars(),100.,target_fraction=target)


def test_new_label_training_excludes_unknown_past_not_future_candidates(monkeypatch):
    rows=[dict(date=f'{i:04}',symbol='AAPL',features=[i%7]*16,signal_price=100.) for i in range(261)]
    market={r['date']:{'AAPL':bars()} for r in rows};market['0008']['AAPL']={};market['0260']['AAPL']={}
    seen=[]
    def fitted(train,cal,test,model,labels):
        assert max(r['date'] for r in train)<min(r['date'] for r in cal)<min(r['date'] for r in test)
        assert '0008' not in {r['date'] for r in train+cal}
        assert all(labels[(r['date'],r['symbol'])]==0 for r in train+cal)
        seen.append((tuple(r['date'] for r in train),tuple(r['date'] for r in cal)))
        return np.repeat(.8,len(test))
    monkeypatch.setattr(research,'fit_predict',fitted)
    before,folds=research.walk(rows,market,'logistic',.01)
    assert before[-1]['date']=='0260' and folds[-1]['known_filled_test']==0
    prices=bars();prices[46]=np.asarray([100.,102.,99.9,100.,1000.]);market['0260']['AAPL']=prices
    after,folds=research.walk(rows,market,'logistic',.01)
    assert before==after and seen[:2]==seen[2:] and folds[-1]['known_filled_test']==1


def test_economics_is_not_a_forecast_or_net_risk_relaxation():
    base=research.economics(.004,10);changed=research.economics(.01,10)
    assert base['ideal_trade_breakeven_win_pct']>85
    assert changed['ideal_trade_breakeven_win_pct']==pytest.approx(60.0100010001)
    assert base['ideal_loss_fraction']==changed['ideal_loss_fraction']


def test_same_candidates_do_not_gain_extra_quantity_and_unknown_never_restarts():
    forecasts=[dict(date=d,symbol='AAPL',probability=.9,signal_price=100.) for d in ('a','b','c')]
    market={d:{'AAPL':bars()} for d in ('a','b','c')}
    old=portfolio(forecasts[:1],market,.65)
    new=portfolio(forecasts[:1],market,.65,target_fraction=.01)
    for key in ('quantity','entry','planned_stop','reserved_usd','stop_fraction'):
        assert old['trades'][0][key]==new['trades'][0][key]
    del market['b']['AAPL'][60]
    unknown=portfolio(forecasts,market,.65,target_fraction=.01)
    assert [d['date'] for d in unknown['daily']]==['a']
    assert all(t['date']=='a' for t in unknown['trades'])
    assert unknown['profit_usd'] is None and unknown['known_prefix_sessions']==1
