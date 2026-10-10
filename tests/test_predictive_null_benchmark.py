import numpy as np
import pytest
import predictive_null_benchmark as research


def rows():
    return [dict(date='a',symbol=s,probability=.9-i*.1,predecision_eligible=True,signal_price=100)
        for i,s in enumerate('ABCDE')]


def chosen(values): return {r['symbol'] for r in values if r['probability']>=.5}


def test_controls_use_only_predecision_pool_and_keep_all_candidates():
    original=rows();selected=research.null_selection(original,11,.75)
    assert chosen(selected)=={'A','B'} and len(selected)==5
    assert selected[0]['forecast_probability']==.9
    assert all(not r['selection_score_is_probability'] for r in selected)
    original[0]['predecision_eligible']=False
    assert chosen(research.null_selection(original,11,.75))=={'B'}


def test_all_eligible_control_ignores_model_probabilities_and_future_payloads():
    original=rows();before=chosen(research.null_selection(original,23))
    for r in original: r.update(probability=.01,future_pnl=1e9,future_features=[1e9])
    after=chosen(research.null_selection(original,23))
    assert before==after and len(after)==3


def test_hash_control_reproducible_without_global_random_state():
    original=rows();before=research.null_selection(original,37)
    saved=np.random.get_state()
    try:
        np.random.seed(999);np.random.random(100)
        after=research.null_selection(list(reversed(original)),37)
    finally: np.random.set_state(saved)
    assert chosen(before)==chosen(after)


def test_unfilled_random_choice_is_not_replaced_by_known_fill():
    original=rows();selected=research.null_selection(original,53)
    first=next(r['symbol'] for r in selected if r['probability']>=.5)
    a=np.tile([100.,100.2,99.8,100.,1000.],(390,1));data={'a':{s:(a.copy(),{}) for s in 'ABCDE'}}
    data['a'][first][0][31]=[102,103,101,102,1000]
    outcome=research.evaluated(selected,data,.5)
    assert len(outcome['trades'])==2 and first not in {t['symbol'] for t in outcome['trades']}
    assert {t['symbol'] for t in outcome['trades']}<=chosen(selected)


def test_duplicate_forecast_rejected():
    r=rows()[0]
    with pytest.raises(ValueError,match='Duplicate'): research.null_selection([r,r],71)


def series(rate):
    equity=100000.;daily=[]
    for i in range(60):
        pnl=equity*rate;equity+=pnl
        daily.append(dict(date=f'{i:04d}',pnl=pnl,equity=equity))
    return dict(daily=daily,profit_usd=equity-100000,active_days=60)


def test_paired_descriptive_bootstrap_uses_identical_observed_calendar_and_normalized_returns():
    model=series(.001);controls=[series(0),series(0)]
    result=research.paired_comparison(model,controls)
    assert result['mean_daily_model_advantage_bps']==pytest.approx(10)
    assert result['descriptive_block_bootstrap_interval_bps']==pytest.approx([10,10])
    assert not result['independent_validation_pass'] and result['seed_results_not_independent_market_samples']
    assert research.paired_comparison(model,controls)==result


def test_bootstrap_rejects_calendar_mismatch():
    model=series(0);control=series(0);control['daily']=control['daily'][1:]
    with pytest.raises(ValueError,match='calendars differ'): research.paired_comparison(model,[control])


def test_reference_outcome_cannot_change_silently():
    original=dict(trades=[],profit_usd=0,active_days=0,active_day_win_rate_pct=None,worst_day_usd=0)
    research.reference_match(original,dict(original))
    with pytest.raises(ValueError,match='outcome changed'):
        research.reference_match(dict(original,profit_usd=1),original)
