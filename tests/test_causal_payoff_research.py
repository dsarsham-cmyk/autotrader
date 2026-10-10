from copy import deepcopy
import numpy as np
import pytest
import causal_payoff_research as research


class Constant:
    def __init__(self,value): self.value=value
    def predict(self,x): return np.repeat(self.value,len(x))


def test_sparse_unknown_past_is_excluded_but_future_candidate_remains(monkeypatch):
    rows = [dict(date=f'{i:04d}',symbol='AAPL',features=[i%7]*16,signal_price=100.) for i in range(261)]
    market = {r['date']:{'AAPL':{k:np.asarray([100.,100.5,99.9,100.,1000.]) for k in range(46,107)}} for r in rows}
    market['0008']['AAPL'] = {}
    market['0260']['AAPL'] = {}
    seen = []
    def amounts(train,cal,outcomes,kind):
        assert max(r['date'] for r in train)<min(r['date'] for r in cal)
        assert all(outcomes[(r['date'],r['symbol'])] is not None for r in train+cal)
        assert '0008' not in {r['date'] for r in train+cal}
        seen.append((tuple(r['date'] for r in train),tuple(r['date'] for r in cal)))
        return dict(gain=Constant(20),loss=Constant(100),gain_offset=0.,loss_offset=0.,
                    gain_train_samples=len(train),loss_train_samples=len(train))
    def probabilities(train,cal,test,kind,labels):
        assert max(r['date'] for r in cal)<min(r['date'] for r in test)
        return np.repeat(.8,len(test))
    monkeypatch.setattr(research,'fit_amounts',amounts)
    monkeypatch.setattr(research,'fit_predict',probabilities)
    before,folds = research.walk(rows,market,'boosted')
    assert before[-1]['date']=='0260' and folds[-1]['known_filled_test']==0
    market['0260']['AAPL'] = {k:np.asarray([100.,100.5,98.,100.,1000.]) for k in range(46,107)}
    after,folds = research.walk(rows,market,'boosted')
    assert before==after and seen[:2]==seen[2:]
    assert folds[-1]['known_filled_test']==1


def test_net_rank_preserves_true_probability_and_uses_only_positive_expectancy():
    rows = [dict(date='2026-09-01',symbol=s,features=[0]*16,signal_price=100.,
                 probability=p,expected_net_return=e) for s,p,e in
            [('AAPL',.95,-.001),('MSFT',.8,.002),('NVDA',.9,.003),('TSLA',.95,.001)]]
    saved = deepcopy(rows)
    selected = research.selection(rows,'positive_expectancy_net_rank',.65)
    scores = {r['symbol']:r['probability'] for r in selected}
    assert scores==pytest.approx(dict(AAPL=0,MSFT=.9,NVDA=1,TSLA=.8))
    assert rows==saved
    assert all(r['forecast_probability']==saved[i]['probability'] and
               r['selection_score_is_probability'] is False for i,r in enumerate(selected))


def test_zero_expectancy_is_not_selected_and_high_true_gate_is_not_ordinal_gate():
    rows = [dict(date='2026-09-01',symbol=s,probability=.95,expected_net_return=e)
            for s,e in [('AAPL',.001),('MSFT',.002),('NVDA',.003),('TSLA',0)]]
    selected = research.selection(rows,'positive_expectancy_net_rank',.9)
    assert sum(r['probability']>=.5 for r in selected)==3
    assert next(r for r in selected if r['symbol']=='TSLA')['probability']==0
    assert any(r['probability']<.9 and r['forecast_probability']>=.9 for r in selected if r['probability']>0)
