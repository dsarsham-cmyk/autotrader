from copy import deepcopy
import numpy as np
import pytest
import daily_meta_research as meta


def records(first,count):
    return [dict(date=f'{i:04d}',features=[float(i%7),float(i%5)],label=i%2,
        base_active=True,base_net_pnl=1 if i%2 else -1) for i in range(first,first+count)]


def test_day_features_do_not_use_future_labels_fills_or_pnl():
    rows=[dict(date='d',symbol=s,features=[float(i),.1],probability=.7+i*.01,
        label=1,filled=True,pnl=10) for i,s in enumerate('ABCD')]
    before=meta.day_features(rows)
    for row in rows: row.update(label=0,filled=False,pnl=-10000)
    assert meta.day_features(rows)==before
    with pytest.raises(ValueError): meta.day_features([])


@pytest.mark.parametrize('kind',['logistic','boosted'])
def test_meta_fit_ignores_test_labels_and_future_activity(kind):
    train,cal,test=records(0,90),records(90,30),records(120,20)
    before=meta.fit_meta(train,cal,test,kind)
    for row in test: row.update(label=1-row['label'],base_active=False,base_net_pnl=-1e9)
    np.testing.assert_allclose(meta.fit_meta(train,cal,test,kind),before)


def test_future_candidate_features_cannot_change_other_meta_predictions():
    train,cal,test=records(0,90),records(90,30),records(120,20)
    before=meta.fit_meta(train,cal,test,'logistic')
    test[-1]['features']=[1e6,-1e6]
    np.testing.assert_allclose(meta.fit_meta(train,cal,test,'logistic')[:-1],before[:-1])


def test_meta_fold_dates_are_strictly_separated(monkeypatch):
    seen=[]
    def predict(train,cal,test,kind):
        assert train[-1]['date']<cal[0]['date']<=cal[-1]['date']<test[0]['date']
        seen.append((train[-1]['date'],test[0]['date']))
        return np.repeat(.7,len(test))
    monkeypatch.setattr(meta,'fit_meta',predict)
    result,folds=meta.meta_crossfit(records(0,161),'logistic')
    assert len(result)==41 and len(folds)==3 and len(seen)==3


def test_insufficient_history_abstains_without_deleting_test_dates():
    data=records(0,140)
    for row in data: row['base_active']=False
    probabilities,folds=meta.meta_crossfit(data,'logistic')
    assert len(probabilities)==20 and all(value is None for value in probabilities.values())
    assert folds[0]['status']=='no_meta_forecast_insufficient_past_evidence'
    rows=[dict(date=date,probability=.8,symbol='A') for date in probabilities]
    gated=meta.gate(rows,probabilities,.65)
    assert len(gated)==20 and all(row['probability']==0 for row in gated)
    assert all(row['probability']==.8 for row in rows)


def test_gate_uses_forecast_only_not_future_pnl():
    rows=[dict(date='a',probability=.8,symbol='A',pnl=-100),
        dict(date='b',probability=.8,symbol='A',pnl=100)]
    gated=meta.gate(rows,dict(a=.9,b=.1),.65)
    assert [row['probability'] for row in gated]==[.8,0]


def test_stock_inner_folds_never_filter_future_rows_by_fill(monkeypatch):
    rows=[dict(date=f'{i:04d}',symbol='A',features=[i],signal_price=100) for i in range(161)]
    data={row['date']:{'A':(np.tile([100.,101.,99.,100.,1000.],(390,1)),{})} for row in rows}
    data['0160']['A'][0][46]=[200,201,199,200,1000]  # future candidate cannot fill
    seen=[]
    def predict(train,cal,test,kind,labels):
        assert max(r['date'] for r in train)<min(r['date'] for r in cal)
        assert max(r['date'] for r in cal)<min(r['date'] for r in test)
        seen.extend(row['date'] for row in test)
        return np.repeat(.7,len(test))
    monkeypatch.setattr(meta,'fit_predict',predict)
    predictions,folds=meta.stock_crossfit(rows,data)
    assert '0160' in seen and len(predictions)==41 and len(folds)==3


def test_future_baseline_path_cannot_change_past_meta_records():
    rows=[dict(date=date,symbol='A',features=[1,2],signal_price=100,probability=.8) for date in ['a','b']]
    data={date:{'A':(np.tile([100.,100.2,99.8,100.,1000.],(390,1)),{})} for date in ['a','b']}
    before=meta.meta_records(rows,data)
    data['b']['A'][0][60]=[50,51,49,50,1000]
    after=meta.meta_records(rows,data)
    assert before[0]==after[0]
    assert before[1]['features']==after[1]['features']
    assert before[1]['base_net_pnl']!=after[1]['base_net_pnl']
