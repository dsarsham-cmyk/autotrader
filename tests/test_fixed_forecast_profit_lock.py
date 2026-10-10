import copy
import pytest
import numpy as np
from fixed_forecast_profit_lock import fixed_quantity_diagnostic
from causal_sparse_simulator import portfolio


def fixture():
    bars={i:np.array([100.,100.2,99.8,100.,1000.]) for i in range(390)}
    bars[46]=np.array([100.,100.35,99.9,100.3,1000.])
    bars[47]=np.array([100.3,100.35,100.25,100.3,1000.])
    bars[48]=np.array([100.25,100.3,100.2,100.25,1000.])
    rows=[dict(date='a',symbol='A',signal_price=100.,probability=.8)]
    market={'a':{'A':bars}}
    return portfolio(rows,market,.65),market


def test_same_entry_quantity_exit_diagnostic_is_not_trading_approval():
    original,market=fixture();before=copy.deepcopy(original)
    result=fixed_quantity_diagnostic(original,market)
    paired=result['paired_trades'][0]
    assert paired['quantity']==original['trades'][0]['quantity']
    assert paired['reason']=='profit_lock' and paired['exit_minute']==48 and result['delta_usd']>0
    assert not result['risk_approved'] and not result['orders'] and original==before


def test_missing_counterfactual_price_does_not_become_zero_pnl():
    original,market=fixture();del market['a']['A'][47]
    r=fixed_quantity_diagnostic(original,market)
    assert r['net_usd'] is None and r['delta_usd'] is None and r['unknown']


def test_aggregate_guard_cannot_be_replaced_by_individual_trade_path():
    original,market=fixture();original['trades'][0]['reason']='account_guard'
    assert fixed_quantity_diagnostic(original,market)['status']=='unavailable_aggregate_guard_context'


def test_changed_entry_or_reference_net_rejected():
    original,market=fixture();original['trades'][0]['entry']+=1.
    with pytest.raises(ValueError,match='entry'): fixed_quantity_diagnostic(original,market)
    original,market=fixture();original['profit_usd']+=1.
    with pytest.raises(ValueError,match='net'): fixed_quantity_diagnostic(original,market)


def test_complete_no_trade_span_stays_flat_not_winning():
    original=dict(full_period_coverage_complete=True,trades=[],profit_usd=0.,costs_bps=10,delay=16,
        daily=[dict(date='a',active=False,pnl=0.)])
    r=fixed_quantity_diagnostic(original,{})
    assert r['active_days']==0 and r['win_rate_pct'] is None and r['net_usd']==0.
