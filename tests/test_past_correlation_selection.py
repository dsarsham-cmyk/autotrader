import copy
import numpy as np
import pytest
from past_correlation_selection import pair_history,select
from causal_sparse_simulator import portfolio


def history():
    return {s:{f'{i:04d}':v for i,v in enumerate(values)} for s,values in
        {'A':np.arange(60,dtype=float),'B':np.arange(60,dtype=float),'C':-np.arange(60,dtype=float)}.items()}


def rows(): return [dict(date='0060',symbol=s,signal_price=100.,probability=p) for s,p in [('A',.9),('B',.8),('C',.7)]]


def test_correlated_candidate_rejected_without_changing_probability():
    r=rows();chosen,evidence=select(r,history(),.65,True)
    assert [c['symbol'] for c in chosen]==['A','C']
    assert chosen[0] is r[0] and chosen[1] is r[2]
    assert evidence[0]['checks'][1]['pairs'][0]['correlation']==pytest.approx(1.)


def test_current_and_future_returns_cannot_change_past_selection():
    h=history();before=select(rows(),h,.65,True)
    for values in h.values(): values.update({'0060':999.,'0061':-999.})
    assert select(rows(),h,.65,True)==before
    assert pair_history(h,'A','B','0060')['latest_history_date']=='0059'


def test_incomplete_or_constant_pair_is_not_imputed_safe():
    h=history();h['B']={k:1. for k in list(h['B'])[:39]}
    assert pair_history(h,'A','B','0060')['correlation'] is None
    chosen,evidence=select(rows(),h,.65,True)
    assert [c['symbol'] for c in chosen]==['A','C']


def test_no_eligible_date_retained_as_no_trade_not_a_win():
    r=rows();chosen,evidence=select(r,history(),.95,True)
    assert chosen==r and evidence[0]['chosen']==[]
    result=portfolio(chosen,{},.95)
    assert len(result['daily'])==1 and result['active_days']==0 and result['active_day_win_rate_pct'] is None


def test_baseline_rank_is_not_correlation_filtered():
    chosen,evidence=select(rows(),{},.65,False)
    assert chosen==rows() and evidence[0]['chosen']==['A','B','C']


def test_missing_selected_future_price_not_used_to_choose_replacement():
    chosen,evidence=select(rows(),history(),.65,True)
    a={i:np.array([100.,100.2,99.8,100.,1000.]) for i in range(390)}
    result=portfolio(chosen,{'0060':{'A':{},'C':a}},.65)
    assert result['profit_usd'] is None and result['unknown_selections'][0]['symbols']==['A']
    assert evidence[0]['chosen']==['A','C']


def test_duplicate_forecasts_fail():
    with pytest.raises(ValueError): select(rows()+[copy.deepcopy(rows()[0])],history(),.65,True)
