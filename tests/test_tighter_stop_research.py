import numpy as np
import tighter_stop_research as research


def data():
    rows=[dict(date=f'{i:04d}',symbol='A',features=[i%7]*4,signal_price=100) for i in range(261)]
    by_date={row['date']:{'A':(np.tile([100.,100.2,99.8,100.,1000.],(390,1)),{})} for row in rows}
    for i,row in enumerate(rows):
        a=by_date[row['date']]['A'][0]
        if i%2: a[60,1]=101
        if i%4==1: a[50,2]=99.6
    return rows,by_date


def test_models_are_refitted_to_each_stop_labels_with_past_only_splits(monkeypatch):
    rows,by_date=data();seen=[]
    def predict(train,cal,test,kind,labels):
        assert train[-1]['date']<cal[0]['date']<=cal[-1]['date']<test[0]['date']
        seen.append(labels[('0001','A')])
        return np.repeat(.7,len(test))
    monkeypatch.setattr(research,'fit_predict',predict)
    old,_=research.walk(rows,by_date,.01,'logistic')
    tight,_=research.walk(rows,by_date,.0025,'logistic')
    assert len(old)==len(tight)==21 and seen==[1,1,0,0]


def test_future_test_labels_do_not_change_any_fit(monkeypatch):
    rows,by_date=data()
    def predict(train,cal,test,kind,labels):
        return np.repeat(np.mean([labels[(r['date'],r['symbol'])] for r in train+cal]),len(test))
    monkeypatch.setattr(research,'fit_predict',predict)
    before,_=research.walk(rows,by_date,.005,'logistic')
    by_date['0260']['A'][0][60,1]=101
    after,_=research.walk(rows,by_date,.005,'logistic')
    assert before==after
