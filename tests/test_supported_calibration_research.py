import numpy as np
import pytest
from supported_calibration_research import smoothed_calibrator,fold_predict
from predictive_portfolio_research import fit_predict


def test_past_bins_smoothed_monotone_and_future_batch_independent():
    scores=np.arange(100,dtype=float)
    labels=np.r_[np.zeros(50),np.ones(50)]
    dates=[str(i//2) for i in range(100)]
    model,bins=smoothed_calibrator(scores,labels,dates)
    assert len(bins)==5 and sum(b['count'] for b in bins)==100
    assert all(b['distinct_days']==10 for b in bins)
    p=model.predict([-100,0,50,100,1e9])
    assert np.diff(p).min()>=0 and 0<p.min()<=p.max()<1
    assert model.predict([100])[0]==p[-2]
    assert p[-1]==p[-2]


def test_tied_scores_keep_all_counts_without_artificial_certainty():
    model,bins=smoothed_calibrator([1]*10,[1]*10,['past']*10)
    assert len(bins)==1 and bins[0]['count']==10
    assert model.predict([-1,1,100]).tolist()==pytest.approx([11/12]*3)
    for scores,labels,dates in [([],[],[]),([float('nan')],[1],['d']),([1],[2],['d']),([1],[1],[])]:
        with pytest.raises(ValueError): smoothed_calibrator(scores,labels,dates)


def test_same_or_future_calibration_dates_rejected():
    row=dict(date='2026-01-01',symbol='A',features=[0])
    with pytest.raises(ValueError,match='past'): fold_predict([row],[row],[row],'logistic',{})


def test_original_control_exact_and_future_candidate_cannot_change_prediction():
    rows=[dict(date=f'{i:04}',symbol='A',features=[i%3,i%7]) for i in range(42)]
    train,cal,test=rows[:30],rows[30:40],rows[40:]
    labels={(r['date'],r['symbol']):i%2 for i,r in enumerate(rows[:40])}
    control,probabilities,bins=fold_predict(train,cal,test,'logistic',labels)
    assert np.allclose(control,fit_predict(train,cal,test,'logistic',labels),rtol=0,atol=1e-12)
    test2=[test[0],dict(test[1],features=[1e6,-1e6])]
    control2,probabilities2,bins2=fold_predict(train,cal,test2,'logistic',labels)
    assert control[0]==control2[0] and probabilities[0]==probabilities2[0] and bins==bins2
