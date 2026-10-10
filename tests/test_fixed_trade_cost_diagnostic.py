import pytest
import json
from fixed_trade_cost_diagnostic import trade_record,diagnostic,run


def outcome(trades):
    return dict(trades=trades,profit_usd=sum(t['pnl'] for t in trades),
        daily=[dict(date=d,active=True) for d in sorted({t['date'] for t in trades})])


def test_gross_and_costs_reconcile():
    t=trade_record('a','A',10,100*1.001,101*.999,.001,'target')
    assert t['gross_pnl']==pytest.approx(10)
    assert t['cost_drag']==pytest.approx(2.01)
    result=diagnostic(outcome([t]))
    assert result['variants'][0]['profit_usd']==pytest.approx(10)
    assert result['variants'][4]['profit_usd']==pytest.approx(t['pnl'])
    assert all(v['active_days']==1 for v in result['variants'])


def test_costs_cannot_increase_fixed_trade_profit():
    t=trade_record('a','A',10,100.1,98*.999,.001,'account_guard')
    profits=[v['profit_usd'] for v in diagnostic(outcome([t]))['variants']]
    assert profits==sorted(profits,reverse=True)


def test_abstention_not_win():
    result=diagnostic(outcome([]))
    assert all(v['active_day_win_rate_pct'] is None for v in result['variants'])


def test_missing_evidence_fails_closed():
    with pytest.raises(ValueError):
        diagnostic(dict(trades=[dict(date='a',pnl=1)],daily=[dict(date='a',active=True)],profit_usd=1))


def test_bad_reconciliation_rejected():
    t=trade_record('a','A',1,100.1,100*.999,.001,'stop')
    bad=outcome([t]);bad['profit_usd']=100
    with pytest.raises(ValueError): diagnostic(bad)


def test_diagnostic_honors_delayed_protocol_and_preserves_case_identity(tmp_path):
    t=trade_record('a','A',1,100.1,101*.999,.001,'target')
    delayed=dict(outcome([t]),costs_bps=10,delay=16,threshold=.65)
    immediate=dict(delayed,delay=1)
    source=dict(protocol={'entry_delay':16},cases=[dict(model='boosted',minute=30,
        horizon='target_60',feature_set='extended',gate='mean',outcomes=[immediate,delayed])])
    path=tmp_path/'input.json';path.write_text(json.dumps(source))
    result=run([path],tmp_path/'output.json')
    assert len(result['cases'])==1
    assert result['cases'][0]['entry_delay']==16
    assert result['cases'][0]['feature_set']=='extended'
    assert result['cases'][0]['gate']=='mean'
