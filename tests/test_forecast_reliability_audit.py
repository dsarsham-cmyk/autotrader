import pytest
from forecast_reliability_audit import summarize,inspect_case


def test_bins_partition_exact_boundaries_no_empty_success():
    rows=[dict(date='one',symbol=str(i),probability=p,label=1)
          for i,p in enumerate([0,.5,.65,.8,.9,1])]
    report=summarize(rows)
    assert [b['count'] for b in report['bins']]==[1,1,1,1,2]
    assert report['distinct_days']==1 and not report['independent_validation_pass']
    empty=summarize([])
    assert empty['brier'] is None and empty['observed_positive_fraction'] is None
    assert all(b['mean_probability'] is None for b in empty['bins'])


def test_overconfidence_and_invalid_inputs_not_hidden():
    rows=[dict(date=str(i),symbol='A',probability=.9,label=0) for i in range(3)]
    result=summarize(rows)
    assert result['brier']==pytest.approx(.81)
    assert result['expected_calibration_error']==pytest.approx(.9)
    for p in [True,float('nan'),1.01,-.01]:
        with pytest.raises(ValueError): summarize([dict(rows[0],probability=p)])
    with pytest.raises(ValueError): summarize(rows+[rows[0]])


def test_unknown_is_not_unfilled_or_losing_day(monkeypatch):
    forecasts=[dict(date=str(i),symbol='A',signal_price=100,probability=.9) for i in range(3)]
    outcomes=iter([None,dict(filled=False),dict(filled=True,label=1)])
    monkeypatch.setattr('forecast_reliability_audit.path',lambda *a,**k:next(outcomes))
    case=dict(model='test',target_fraction=.01,forecasts=forecasts,
        outcomes=[dict(threshold=.65,costs_bps=10,delay=16,trades=[],full_period_coverage_complete=False,
                       profit_usd=None,active_days=0,active_day_win_rate_pct=None)])
    result=inspect_case(case,{})
    assert len(result['unknown_paths'])==1 and result['known_unfilled']==1
    assert result['standalone_known_filled']['count']==1
    assert result['executed_primary_gate065']['count']==0
    assert result['primary_net_usd'] is None
