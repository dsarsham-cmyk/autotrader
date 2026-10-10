from copy import deepcopy
import pytest
from split_predictive_research import assert_reference, flatten


def test_flatten_preserves_all_candidates_and_orders_dates_symbols():
    rows = {'2026-09-02':{'B':{'symbol':'B'},'A':{'symbol':'A'}},
            '2026-09-01':{'C':{'symbol':'C'}}}
    assert [r['symbol'] for r in flatten(rows)] == ['C','A','B']


def test_reference_comparison_rejects_net_trades_daily_or_unknown_change():
    reference = dict(profit_usd=-1,daily=[{'profit_usd':-1}],trades=[{'symbol':'A'}],unknown_selections=[])
    assert_reference(deepcopy(reference),reference)
    for key,value in [('profit_usd',1),('daily',[]),('trades',[]),('unknown_selections',[{}])]:
        changed = deepcopy(reference)
        changed[key] = value
        with pytest.raises(ValueError,match='not reproduced'):
            assert_reference(changed,reference)


def test_unknown_full_result_cannot_be_replaced_by_known_prefix_profit():
    reference = dict(profit_usd=None,daily=[],trades=[],unknown_selections=[{'symbol':'A'}])
    assert_reference(deepcopy(reference),reference)
    with pytest.raises(ValueError):
        assert_reference(dict(reference,profit_usd=0),reference)
