import numpy as np
import pytest
import opening_path_research as research


def bars(): return np.tile([100.,101.,99.,100.,1000.],(390,1))


def data():
    return {f'{i:04d}':{'A':(bars(),dict(prior_dollars=3e7,relative_volume=1))} for i in range(26)}


def test_current_features_ignore_every_post_cutoff_price_and_volume():
    source=data();before=research.path_rows(source)
    source['0025']['A'][0][30:]=[200,210,190,200,1e9]
    after=research.path_rows(source)
    assert before==after and len(before[-1]['features'])==141


def test_minute_volume_uses_only_prior_same_minute_opening_history():
    opening=bars()[:30];past=np.full((20,30),1000.)
    feature=np.asarray(research.ordered_features(opening,past)).reshape(30,4)
    assert feature[:,3]==pytest.approx(np.log(2))
    past[:,5]*=2
    changed=np.asarray(research.ordered_features(opening,past)).reshape(30,4)
    assert changed[5,3]==pytest.approx(np.log(1.5))
    assert np.array_equal(feature[:5],changed[:5])


def test_minute_order_is_preserved_and_no_outcome_fields_enter_features():
    a=bars()[:30].copy();a[7,3]=100.5
    features=np.asarray(research.ordered_features(a,np.full((20,30),1000.))).reshape(30,4)
    assert features[7,0]>0 and features[8,0]<0
    assert features[7,2]>0 and features[6,0]==0


@pytest.mark.parametrize('bad',['shape','negative','nan'])
def test_invalid_path_fails_closed(bad):
    a=bars()[:30];past=np.full((20,30),1000.)
    if bad=='shape': past=past[:-1]
    if bad=='negative': a[3,4]=-1
    if bad=='nan': past[0,0]=np.nan
    with pytest.raises(ValueError): research.ordered_features(a,past)


@pytest.mark.parametrize('kind',['logistic','mlp'])
def test_scaler_model_calibrator_never_fit_on_future_features_or_labels(kind):
    rng=np.random.default_rng(19)
    rows=[dict(date=f'{i:04d}',symbol='A',features=rng.normal(size=4).tolist()) for i in range(160)]
    labels={(r['date'],'A'):i%2 for i,r in enumerate(rows)}
    before,metadata=research.fit_probability(rows[:100],rows[100:140],rows[140:],labels,kind)
    rows[-1]['features']=[1e6]*4;labels[(rows[-1]['date'],'A')]=1-labels[(rows[-1]['date'],'A')]
    after,_=research.fit_probability(rows[:100],rows[100:140],rows[140:],labels,kind)
    assert np.allclose(before[:-1],after[:-1])
    assert metadata['scaler_fit_on_train_only'] and not metadata['random_test_split_used']
    if kind=='mlp': assert metadata['fitted_iterations']==[100]


def test_fit_rejects_overlapping_calibration_test():
    rows=[dict(date=f'{i:04d}',symbol='A',features=[i%2]) for i in range(160)]
    labels={(r['date'],'A'):i%2 for i,r in enumerate(rows)}
    with pytest.raises(ValueError,match='overlap'):
        research.fit_probability(rows[:100],rows[100:140],rows[130:],labels,'logistic')


def test_walk_only_filters_past_fills_and_passes_all_future_candidates(monkeypatch):
    rows=[dict(date=f'{i:04d}',symbol='A',features=[1],signal_price=100) for i in range(261)]
    source={r['date']:{'A':(bars(),{})} for r in rows}
    # Unknown test fill cannot remove this candidate from prediction.
    source['0260']['A'][0][46]=[102,103,101,102,1000]
    seen=[]
    def fit(train,cal,test,labels,kind):
        assert max(r['date'] for r in train)<min(r['date'] for r in cal)
        assert max(r['date'] for r in cal)<min(r['date'] for r in test)
        seen.extend(r['date'] for r in test)
        return np.full(len(test),.7),{}
    monkeypatch.setattr(research,'fit_probability',fit)
    predictions,_=research.walk(rows,source,'mlp')
    assert len(predictions)==21 and '0260' in seen
