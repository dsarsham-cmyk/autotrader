import pandas as pd
import pytest
from modeled_execution_quote_audit import select_trades,boundary,context_match


def test_sampling_ignores_profit_and_input_order():
    rows=[dict(date=f'2025-01-{i:02}',symbol='AAPL',pnl=i) for i in range(1,20)]
    expected=[(r['date'],r['symbol']) for r in select_trades(rows,5)]
    assert expected==[(r['date'],r['symbol']) for r in select_trades([dict(r,pnl=-1000*r['pnl']) for r in rows[::-1]],5)]
    with pytest.raises(ValueError): select_trades(rows+rows[:1])


def test_boundaries_dst_and_invalid_minutes():
    base=dict(date='2025-01-21',entry_minute=46,exit_minute=47)
    assert boundary(base,'entry').isoformat()=='2025-01-21T15:16:00+00:00'
    assert boundary(dict(base,date='2025-07-21'),'entry').isoformat()=='2025-07-21T14:16:00+00:00'
    for updates in ({'entry_minute':47},{'exit_minute':107},{'exit_minute':45},{'entry_minute':46.0}):
        with pytest.raises(ValueError): boundary(dict(base,**updates),'entry')


def test_context_has_no_fill_or_real_cost_claim():
    point=pd.Timestamp('2025-01-21T15:16:00Z')
    quote=dict(t=point.isoformat(),bp=100,ap=100.01,bs=1,**{'as':1})
    result=context_match(point,[quote,dict(quote,t=(point+pd.Timedelta(seconds=1)).isoformat(),ap=999)])
    assert result['status']=='observed_fresh_model_boundary_quote'
    assert not result['total_real_cost_measured'] and not result['actual_execution_time_authenticated']
    assert not any('fill' in k for k in result)
    assert context_match(point,[quote,dict(quote,ap=101)])['status']=='ambiguous_terminal_quote'
    assert context_match(point,[dict(quote,t=(point-pd.Timedelta(seconds=3)).isoformat())])['status']=='stale_terminal_quote'
    assert context_match(point,[dict(quote,bp=0)])['status']=='invalid_terminal_quote'
