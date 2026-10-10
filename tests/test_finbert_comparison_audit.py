import copy
import pytest
from finbert_comparison_audit import audit,check,ARMS,MODELS,AXES,RISK


def outcome(axis):
    return dict(threshold=axis[0],costs_bps=axis[1],delay=axis[2],orders=False,
        production_approved=False,independent_validation_pass=False,
        daily=[dict(date='2026-10-12',pnl=-1.,equity=99999.,active=True)],
        trades=[dict(date='2026-10-12',pnl=-1.)],known_prefix_profit_usd=-1.,profit_usd=-1.,
        active_days=1,active_day_win_rate_pct=0.,full_period_coverage_complete=True,
        unknown_selections=[],expected_forecast_sessions=1,target_screen_pass=False,
        known_prefix_metrics={k:True for k in RISK})


def fixture():
    return dict(status='completed_exposed_finbert_input_ablation',orders=False,
        production_approved=False,independent_validation_pass=False,cases=[dict(
            feature_set=a,model=m,folds=[dict(test_first='2026-10-12',test_last='2026-10-12')],
            outcomes=[outcome(axis) for axis in sorted(AXES)]) for a in ARMS for m in MODELS])


def calendar(): return {'2026-10-12':dict(date='2026-10-12',open='09:30',close='16:00')}


def test_all_predeclared_pairs_reconcile_without_promotion():
    result=audit(fixture(),calendar())
    assert len(result['paired_variants'])==18
    assert all(p['net_delta_usd']==0 for p in result['paired_variants'])
    assert not result['independent_validation_pass'] and not result['orders']


@pytest.mark.parametrize('mutation',['missing_case','duplicate_case','missing_variant','duplicate_variant'])
def test_incomplete_or_duplicated_axes_rejected(mutation):
    r=fixture()
    if mutation=='missing_case': r['cases'].pop()
    if mutation=='duplicate_case': r['cases'].append(copy.deepcopy(r['cases'][0]))
    if mutation=='missing_variant': r['cases'][0]['outcomes'].pop()
    if mutation=='duplicate_variant': r['cases'][0]['outcomes'].append(copy.deepcopy(r['cases'][0]['outcomes'][0]))
    with pytest.raises(ValueError): audit(r,calendar())


def test_trade_ledger_and_win_rate_cannot_disagree():
    o=outcome((.5,10,16));o['trades'][0]['pnl']=1.
    with pytest.raises(ValueError,match='reconciliation'): check(o)
    o=outcome((.5,10,16));o['active_day_win_rate_pct']=100.
    with pytest.raises(ValueError,match='Win rate'): check(o)


def test_partial_outcomes_do_not_create_economic_delta():
    r=fixture()
    for c in r['cases']:
        for o in c['outcomes']:
            o.update(full_period_coverage_complete=False,profit_usd=None,active_day_win_rate_pct=None)
    result=audit(r,calendar())
    assert all(p['net_delta_usd'] is None for p in result['paired_variants'])


def test_no_trade_is_not_a_winning_day():
    o=outcome((.5,10,16));o.update(trades=[],active_days=0,profit_usd=0.,known_prefix_profit_usd=0.,active_day_win_rate_pct=None)
    o['daily']=[dict(date='2026-10-12',pnl=0.,equity=100000.,active=False)]
    assert check(o)


def test_favorable_screen_flag_cannot_override_actual_losses():
    o=outcome((.5,10,16));o['target_screen_pass']=True
    with pytest.raises(ValueError,match='Target screen'): check(o)
