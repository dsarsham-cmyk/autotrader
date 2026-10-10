import numpy as np
from regime_predictive_research import extended_rows,forecasts,vwap


def data():
    return {f'{i:04d}':{'A':(np.tile([100,101,99,100,1000.],(390,1)),
        dict(prior_dollars=3e7,relative_volume=1))} for i in range(26)}


def test_after_decision_prices_and_volume_not_in_features():
    by_date=data(); original=extended_rows(by_date)
    by_date['0025']['A'][0][30:,:]=[200,210,190,200,1e9]
    assert original[-1]['features']==extended_rows(by_date)[-1]['features']


def test_only_past_volume_sets_relative_volume():
    by_date=data();original=extended_rows(by_date)
    by_date['0025']['A'][0][:30,4]*=2
    modified=extended_rows(by_date)
    assert modified[-1]['features'][14]==2*original[-1]['features'][14]
    assert original[-2]['features']==modified[-2]['features']


def test_vwap_constant_prices():
    assert vwap(data()['0000']['A'][0],30)==100


def test_prediction_does_not_fit_on_test_features_or_labels():
    rng=np.random.default_rng(33)
    rows=[dict(date=str(i),symbol='A',features=rng.normal(size=21)) for i in range(160)]
    outcomes={(r['date'],'A'):dict(entry=100,exit=100+(1 if i%2 else -2)) for i,r in enumerate(rows)}
    before=forecasts(rows[:100],rows[100:140],rows[140:],outcomes)
    rows[-1]['features']=np.full(21,1e6)
    outcomes[(rows[-1]['date'],'A')]['exit']=1e9
    after=forecasts(rows[:100],rows[100:140],rows[140:],outcomes)
    for key in before:
        assert np.allclose(before[key][:-1],after[key][:-1])
