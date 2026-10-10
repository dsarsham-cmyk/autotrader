import numpy as np
import pytest
import conditional_payoff_research as research
from tighter_stop_simulator import portfolio


class Constant:
    def __init__(self,value): self.value=value
    def predict(self,x): return np.repeat(self.value,len(x))


def fitted(gain=.002,loss=.01):
    return dict(gain=Constant(gain*10000),loss=Constant(loss*10000),gain_offset=0,loss_offset=0)


def test_probability_alone_does_not_imply_positive_expectancy():
    forecast=research.predict_amounts(fitted(),[dict(features=[1])]*2,[.8,.9])
    assert forecast['expected_net_return']==pytest.approx([-.0004,.0008])


def test_negative_amount_predictions_are_clipped_not_invented_gains():
    forecast=research.predict_amounts(fitted(-.1,-.1),[dict(features=[1])],[.9])
    assert forecast['conditional_gain'][0]==forecast['conditional_loss'][0]==0
    with pytest.raises(ValueError): research.predict_amounts(fitted(),[dict(features=[1])],[1.1])


def row(symbol,p,ev):
    return dict(date='day',symbol=symbol,probability=p,expected_net_return=ev,
        signal_price=100,features=[1])


def chosen(rows):
    return [r['symbol'] for r in sorted(rows,key=lambda r:-r['probability']) if r['probability']>=.5]


def test_matched_selectors_preserve_genuine_probabilities_and_all_dates():
    rows=[row('A',.95,-.001),row('B',.8,.003),row('C',.9,.001),row('D',.7,.004)]
    plain=research.selection(rows,'probability_only',.5)
    positive=research.selection(rows,'positive_expectancy_probability_rank',.5)
    net=research.selection(rows,'positive_expectancy_net_rank',.5)
    assert chosen(plain)==['A','C','B']
    assert chosen(positive)==['C','B','D']
    assert chosen(net)==['D','B','C']
    assert len(net)==len(rows) and net[0]['forecast_probability']==.95
    assert all(r['selection_score_is_probability'] is False for r in net)
    abstain=research.selection(rows,'positive_expectancy_net_rank',.99)
    assert len(abstain)==4 and chosen(abstain)==[]


def test_no_replacement_after_learning_a_top_three_order_did_not_fill():
    rows=[row(s,.9-i*.01,.001) for i,s in enumerate('ABCD')]
    selected=research.selection(rows,'probability_only',.5)
    bars=np.tile([100.,100.2,99.8,100.,1000.],(390,1))
    data={'day':{s:(bars.copy(),{}) for s in 'ABCD'}}
    data['day']['A'][0][46]=[102,102.2,101.8,102,1000]
    result=portfolio(selected,data,.01,.5)
    assert {t['symbol'] for t in result['trades']}=={'B','C'}


def test_duplicate_and_nonfinite_selector_inputs_fail_closed():
    r=row('A',.9,.001)
    with pytest.raises(ValueError,match='Duplicate'): research.selection([r,r],'probability_only',.5)
    with pytest.raises(ValueError): research.selection([dict(r,expected_net_return=float('nan'))],'probability_only',.5)


def fixture():
    train=[dict(date='a',symbol=str(i),features=[i%2]) for i in range(100)]
    cal=[dict(date='b',symbol=str(i),features=[i%2]) for i in range(40)]
    outcomes={(r['date'],r['symbol']):dict(entry=100,exit=100.2 if int(r['symbol'])%2 else 99,
        filled=True) for r in train+cal}
    return train,cal,outcomes


@pytest.mark.parametrize('kind',['logistic_ridge','boosted'])
def test_separate_conditional_heads_learn_gain_loss_not_signed_average(kind):
    train,cal,outcomes=fixture()
    fit=research.fit_amounts(train,cal,outcomes,kind)
    prediction=research.predict_amounts(fit,[dict(features=[0])],[.9])
    assert prediction['conditional_gain'][0]==pytest.approx(.002)
    assert prediction['conditional_loss'][0]==pytest.approx(.01)
    assert prediction['expected_net_return'][0]==pytest.approx(.0008)
    assert fit['gain_train_samples']==fit['loss_train_samples']==50


def test_only_strictly_past_filled_samples_are_accepted():
    train,cal,outcomes=fixture()
    with pytest.raises(ValueError,match='chronology'): research.fit_amounts(cal,train,outcomes,'boosted')
    outcomes[('a','0')]['filled']=False
    with pytest.raises(ValueError,match='filled'): research.fit_amounts(train,cal,outcomes,'boosted')


def test_future_outcomes_cannot_change_fit_or_forecasts(monkeypatch):
    rows=[dict(date=f'{i:04d}',symbol='A',features=[i%7],signal_price=100) for i in range(261)]
    data={r['date']:{'A':(np.tile([100.,100.2,99.8,100.,1000.],(390,1)),{})} for r in rows}
    seen=[]
    def amounts(train,cal,outcomes,kind):
        assert max(r['date'] for r in train)<min(r['date'] for r in cal)
        mean=np.mean(research.net_returns(train+cal,outcomes))
        seen.append(mean)
        return fitted(.002,abs(mean))
    def probability(train,cal,test,kind,labels):
        assert max(r['date'] for r in cal)<min(r['date'] for r in test)
        return np.repeat(np.mean([labels[(r['date'],r['symbol'])] for r in train+cal]),len(test))
    monkeypatch.setattr(research,'fit_amounts',amounts)
    monkeypatch.setattr(research,'fit_predict',probability)
    before,_=research.walk(rows,data,'boosted')
    data['0260']['A'][0][60,1]=101
    after,_=research.walk(rows,data,'boosted')
    assert before==after and seen[:2]==seen[2:]
