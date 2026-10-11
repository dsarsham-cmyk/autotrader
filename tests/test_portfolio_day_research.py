from copy import deepcopy
import numpy as np
import pytest
from portfolio_day_research import day_features,schedule,apply_permission,fit_day


def fixture():
    forecasts=[dict(date=f'{i:04}',symbol='A',features=[i%7]*16,probability=.8,signal_price=100) for i in range(130)]
    daily=[dict(date=f'{i:04}',active=True,pnl=1 if i%2 else -1) for i in range(130)]
    return forecasts,daily


def test_current_future_outcomes_and_candidate_cannot_change_current_day(monkeypatch):
    forecasts,daily=fixture();seen=[]
    def fitted(train,cal,future,features,labels):
        assert max(train)<min(cal)<min(future)
        seen.append(([labels[d] for d in train],[labels[d] for d in cal]))
        return np.repeat(.8,len(future))
    monkeypatch.setattr('portfolio_day_research.fit_day',fitted)
    before,folds=schedule(forecasts,daily)
    for d in daily[90:]: d['pnl']*=-1
    forecasts[-1]['features']=[1e6]*16
    after,_=schedule(forecasts,daily)
    assert before[90]==after[90] and seen[0]==seen[2]
    assert all(d['day_probability'] is None for d in before[:90])


def test_permission_preserves_stock_forecasts_without_mutation():
    forecasts,_=fixture();saved=deepcopy(forecasts)
    decisions=[dict(date=f['date'],day_probability=.8) for f in forecasts]
    selected=apply_permission(forecasts,decisions,.9)
    assert forecasts==saved and all(f['probability']==0 for f in selected)
    assert all(f['forecast_probability']==.8 and f['zero_score_is_permission_not_probability'] for f in selected)
    assert all(f['signal_price']==100 for f in selected)
    with pytest.raises(ValueError): apply_permission(forecasts,decisions[:-1],.9)


def test_sparse_active_support_not_fake_success_and_day_features_causal():
    forecasts,daily=fixture()
    for d in daily: d.update(active=False,pnl=0)
    decisions,folds=schedule(forecasts,daily)
    assert all(d['day_probability'] is None for d in decisions)
    assert all(f['reason']=='insufficient_past_active_support' for f in folds)
    before=day_features(forecasts)
    forecasts[-1]['probability']=.1
    after=day_features(forecasts)
    assert before['0000']==after['0000']
    with pytest.raises(ValueError): day_features(forecasts+[forecasts[0]])


def test_actual_day_classifier_does_not_require_future_labels_or_batch_statistics():
    dates=[f'{i:04}' for i in range(50)]
    features={d:[i%3,i%7] for i,d in enumerate(dates)}
    labels={d:i%2 for i,d in enumerate(dates[:45])}
    before=fit_day(dates[:30],dates[30:45],dates[45:47],features,labels)
    features[dates[46]]=[1e6,-1e6]
    after=fit_day(dates[:30],dates[30:45],dates[45:47],features,labels)
    assert before[0]==after[0]
    with pytest.raises(ValueError,match='past'): fit_day(dates[:30],dates[29:45],dates[45:47],features,labels)
