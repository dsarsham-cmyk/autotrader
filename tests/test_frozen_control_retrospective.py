from datetime import date,timedelta
import numpy as np
import pytest
import frozen_control_retrospective as retrospective


def data():
    first=date(2026,6,1)
    return {str(first+timedelta(days=i)):{symbol:(np.tile([100.,101.,99.,100.,1e6],(390,1)),
        dict(prior_dollars=3e7,relative_volume=1))
        for symbol in retrospective.SYMBOLS} for i in range(24)}


def test_retrospective_prediction_uses_only_opening_and_prior_days(monkeypatch):
    by_date=data();target=sorted(by_date)[-1]
    model=dict(trained_through='2026-06-22',fitted={})
    def predict(fitted,rows):
        return dict(probability=np.array([row['features'][0]+.5 for row in rows]))
    monkeypatch.setattr(retrospective,'predict_forecasters',predict)
    before,_=retrospective.retrospective_predictions(by_date,model,target,target)
    by_date[target]['AAPL'][0][30:,:4]*=2
    after,_=retrospective.retrospective_predictions(by_date,model,target,target)
    assert before==after


def test_retrospective_dates_before_training_rejected():
    with pytest.raises(ValueError,match='follow training'):
        retrospective.retrospective_predictions({},dict(trained_through='2026-10-01'),
            '2026-09-30','2026-10-09')


def test_incomplete_universe_recorded_not_silently_counted(monkeypatch):
    by_date=data();target=sorted(by_date)[-1];del by_date[target]['AAPL']
    monkeypatch.setattr(retrospective,'predict_forecasters',lambda *a:pytest.fail('Incomplete packet must not predict'))
    rows,excluded=retrospective.retrospective_predictions(by_date,dict(trained_through='2026-06-22'),target,target)
    assert not rows and excluded[0]['missing_symbols']==['AAPL']
