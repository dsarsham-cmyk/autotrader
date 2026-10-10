import numpy as np
from causal_sparse_simulator import portfolio
from finbert_predictive_research import prefix_accounting


def test_unknown_later_selection_reconciles_only_known_prefix():
    rows=[dict(date=d,symbol='A',signal_price=100.,probability=.8) for d in ['a','b']]
    a=np.tile([100.,100.2,99.8,100.,1000.],(390,1));a[60,1]=101.
    mapping={i:r.copy() for i,r in enumerate(a)}
    result=portfolio(rows,{'a':{'A':mapping},'b':{'A':{}}},.65)
    assert result['profit_usd'] is None and not result['full_period_coverage_complete']
    metrics=prefix_accounting(result,rows)
    assert metrics['final_virtual_equity']==result['daily'][-1]['equity']
    assert result['profit_usd'] is None and result['active_day_win_rate_pct'] is None
    assert len(result['daily'])==1 and not result['target_screen_pass']


def test_unknown_first_selection_has_zero_known_prefix_not_full_result():
    rows=[dict(date='a',symbol='A',signal_price=100.,probability=.8)]
    result=portfolio(rows,{'a':{'A':{}}},.65)
    metrics=prefix_accounting(result,rows)
    assert metrics['final_virtual_equity']==100000. and metrics['winning_active_days']==0
    assert result['profit_usd'] is None and result['daily']==[]
