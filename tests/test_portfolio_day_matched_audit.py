import pytest
from portfolio_day_matched_audit import control_schedule,compare


def test_matched_controls_use_warmup_and_past_support_not_score_threshold():
    decisions=[dict(date=f'{i:04}',day_probability=.1 if i>=90 else None) for i in range(100)]
    decisions[95]['day_probability']=None
    warmup=control_schedule(decisions,'warmup_only')
    support=control_schedule(decisions,'past_support_matched')
    assert sum(d['day_probability'] is not None for d in warmup)==10
    assert sum(d['day_probability'] is not None for d in support)==9
    assert support[94]['day_probability']==1 and support[95]['day_probability'] is None
    with pytest.raises(ValueError): control_schedule(decisions+[decisions[0]],'warmup_only')


def test_comparison_does_not_invent_win_rate_for_empty_or_unknown():
    control=dict(daily=[dict(date='d')],full_period_coverage_complete=True,profit_usd=-10,
                 active_days=2,active_day_win_rate_pct=50)
    filtered=dict(control,profit_usd=0,active_days=0,active_day_win_rate_pct=None)
    result=compare(filtered,control)
    assert result['net_delta_usd']==10 and result['filtered_mean_net_per_active_day'] is None
    assert result['filtered_win_pct'] is None and not result['independent_validation_pass']
    unknown=dict(filtered,full_period_coverage_complete=False,profit_usd=None)
    assert compare(unknown,control)['net_delta_usd'] is None
    with pytest.raises(ValueError): compare(dict(filtered,daily=[]),control)
