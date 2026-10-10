from copy import deepcopy
import numpy as np
import pandas as pd
import pytest
from recency_predictor import fit,past_weights,weight_summary


def fixture():
    dates = pd.bdate_range('2025-01-02',periods=120).strftime('%Y-%m-%d').tolist()
    rows = [dict(date=d,symbol='A',features=[np.sin(i),np.cos(i),i%5,(i%7)/7])
            for i,d in enumerate(dates)]
    labels = {(r['date'],r['symbol']):i%2 for i,r in enumerate(rows)}
    return dates,rows[:80],rows[80:100],rows[100:],labels


def test_half_life_ratio_and_mean_mass_are_exact():
    dates,train,cal,test,labels = fixture()
    weights = past_weights([train[0],train[60]],dates[:100],dates[100],60)
    assert weights[1]/weights[0] == pytest.approx(2)
    assert weights.mean() == pytest.approx(1)
    summary = weight_summary(weights,[train[0],train[60]])
    assert summary['row_weight_effective_size'] <= 2
    assert summary['effective_size_is_independent_observation_count'] is False


@pytest.mark.parametrize('kind',['logistic','boosted'])
def test_future_labels_or_other_future_candidate_cannot_change_predictions(kind):
    dates,train,cal,test,labels = fixture()
    before,metadata = fit(train,cal,test,labels,kind,dates[:100],60)
    changed_labels = dict(labels)
    for row in test:
        changed_labels[(row['date'],row['symbol'])] = 1-changed_labels[(row['date'],row['symbol'])]
    after,other = fit(train,cal,test,changed_labels,kind,dates[:100],60)
    assert before == pytest.approx(after) and metadata == other
    changed_test = deepcopy(test)
    changed_test[-1]['features'] = [1e6,-1e6,1e6,-1e6]
    after,other = fit(train,cal,changed_test,labels,kind,dates[:100],60)
    assert before[:-1] == pytest.approx(after[:-1]) and metadata == other
    assert metadata['weight_history_last'] < metadata['forecast_cutoff']


def test_invalid_or_future_weight_history_is_rejected():
    dates,train,cal,test,labels = fixture()
    for history in [dates[:101],list(reversed(dates[:100])),dates[:100]+[dates[99]],[]]:
        with pytest.raises(ValueError):
            past_weights(train,history,dates[100],60)
    with pytest.raises(ValueError):
        past_weights([test[0]],dates[:100],dates[100],60)
    for half_life in [0,30,True,None]:
        with pytest.raises(ValueError):
            past_weights(train,dates[:100],dates[100],half_life)


def test_overlapping_label_partitions_and_one_class_are_rejected():
    dates,train,cal,test,labels = fixture()
    with pytest.raises(ValueError,match='chronology'):
        fit(train+[cal[0]],cal,test,labels,'logistic',dates[:100],60)
    zero = {key:0 for key in labels}
    with pytest.raises(ValueError,match='Two known past'):
        fit(train,cal,test,zero,'logistic',dates[:100],60)


def test_weighted_scaler_matches_direct_past_weighted_mean():
    dates,train,cal,test,labels = fixture()
    probabilities,metadata = fit(train,cal,test,labels,'logistic',dates[:100],120)
    weights = past_weights(train,dates[:100],dates[100],120)
    expected = np.average([r['features'] for r in train],axis=0,weights=weights)
    assert metadata['scaler_mean'] == pytest.approx(expected)
    assert np.all((probabilities>=0)&(probabilities<=1))
    assert metadata['future_labels_used'] is False and metadata['orders'] is False
