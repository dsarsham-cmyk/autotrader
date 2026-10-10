import numpy as np
import pytest
import quote_feature_ablation as ablation


def data():
    rows=[dict(date=f'{i:04d}',symbol='A',features=[float(i%7)],quote_features=[float(i%3)],
        signal_price=100) for i in range(121)]
    by_date={r['date']:{'A':(np.tile([100.,100.2,99.8,100.,1000.],(390,1)),{})} for r in rows}
    for i,r in enumerate(rows):
        if i%2: by_date[r['date']]['A'][0][60,1]=101
    return rows,by_date


def test_matched_arms_same_splits_and_all_future_candidates(monkeypatch):
    rows,by_date=data();by_date['0120']['A'][0][46]=[200,201,199,200,1000]
    seen=[]
    def predict(train,cal,test,kind,labels):
        assert max(r['date'] for r in train)<min(r['date'] for r in cal)
        assert max(r['date'] for r in cal)<min(r['date'] for r in test)
        seen.append((len(train[0]['features']),[r['date'] for r in test]))
        return np.repeat(.7,len(test))
    monkeypatch.setattr(ablation,'fit_predict',predict)
    base,base_folds=ablation.walk(rows,by_date,'logistic',False)
    quoted,quote_folds=ablation.walk(rows,by_date,'logistic',True)
    assert [r['date'] for r in base]==[r['date'] for r in quoted]
    assert len(base)==21 and base[-1]['date']=='0120'
    assert len(base[0]['features'])==1 and len(quoted[0]['features'])==2
    assert base_folds==quote_folds and len(seen)==4


def test_future_outcome_cannot_change_prior_fold_predictions(monkeypatch):
    rows,by_date=data()
    def predict(train,cal,test,kind,labels):
        # Labels are deliberately read only for past train/calibration.
        past=[labels[(r['date'],r['symbol'])] for r in train+cal]
        return np.repeat(np.mean(past),len(test))
    monkeypatch.setattr(ablation,'fit_predict',predict)
    before,_=ablation.walk(rows,by_date,'logistic',True)
    by_date['0120']['A'][0][60]=[50,51,49,50,1000]
    after,_=ablation.walk(rows,by_date,'logistic',True)
    assert before==after


def test_partial_collection_not_treated_as_complete_sample(tmp_path):
    import json
    (tmp_path/'collection_status.json').write_text(json.dumps(dict(plan=dict(protocol=ablation.PROTOCOL,
        dates=['2026-10-01']),windows=[])))
    with pytest.raises(ValueError,match='Collection incomplete'):
        ablation.matched_rows(tmp_path,tmp_path)


@pytest.mark.parametrize('kind',['classical_rbf','quantum_fidelity'])
def test_kernel_arms_use_identical_matched_chronology(kind,monkeypatch):
    rows,by_date=data();calls=[]
    def predict(train,cal,test,labels,model):
        assert train[-1]['date']<cal[0]['date']<=cal[-1]['date']<test[0]['date']
        assert model==kind
        calls.append((len(train[0]['features']),len(test)))
        return np.repeat(.7,len(test))
    monkeypatch.setattr(ablation,'predict_kernel',predict)
    result,_=ablation.walk(rows,by_date,kind,True)
    assert len(result)==21 and calls==[(2,20),(2,1)]
