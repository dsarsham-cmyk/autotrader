from copy import deepcopy
import pytest
from past_frequency_predictor import predict,KINDS


def fixture():
    cal = [dict(date=d,symbol=s,features=[1],signal_price=100)
           for d,s in [('2025-01-02','AAPL'),('2025-01-03','AAPL'),
                       ('2025-01-02','MSFT'),('2025-01-03','MSFT')]]
    test = [dict(date='2025-01-06',symbol=s,features=[2],signal_price=101)
            for s in ['AAPL','MSFT','NVDA']]
    labels = {(r['date'],r['symbol']):int(r['symbol']=='AAPL') for r in cal}
    return cal,test,labels


def test_global_and_shrunk_stock_probabilities_use_only_known_counts():
    cal,test,labels = fixture()
    probabilities,metadata = predict(cal,test,labels,KINDS[0])
    assert probabilities == pytest.approx([.5,.5,.5])
    probabilities,metadata = predict(cal,test,labels,KINDS[1])
    assert probabilities == pytest.approx([12/22,10/22,.5])
    assert metadata['past_known_filled_rows']==4 and metadata['past_wins']==2
    assert metadata['uncertainty_certified'] is False and metadata['orders'] is False


@pytest.mark.parametrize('kind',KINDS)
def test_future_labels_prices_features_or_candidates_do_not_change_existing_predictions(kind):
    cal,test,labels = fixture()
    before,metadata = predict(cal,test,labels,kind)
    changed = deepcopy(test)
    changed[0].update(features=[1e9],signal_price=1e9)
    future_labels = dict(labels,**{})
    future_labels.update({(r['date'],r['symbol']):1 for r in test})
    after,other = predict(cal,changed,future_labels,kind)
    assert before == pytest.approx(after) and metadata==other
    changed.append(dict(date='2026-01-01',symbol='TSLA',features=[-1e9],signal_price=1))
    after,other = predict(cal,changed,future_labels,kind)
    assert before == pytest.approx(after[:len(before)]) and metadata==other


def test_all_win_or_all_loss_samples_still_have_smoothed_interior_probabilities():
    cal,test,labels = fixture()
    for value in [0,1]:
        p,metadata = predict(cal,test,{k:value for k in labels},KINDS[0])
        assert all(0<v<1 for v in p)
        assert p[0] == pytest.approx((4*value+1)/6)


def test_future_duplicate_unknown_symbol_or_missing_outcome_is_rejected():
    cal,test,labels = fixture()
    for invalid in [cal+[cal[0]],cal+[dict(cal[0],date='2025-01-06')],
                    cal+[dict(cal[0],symbol='UNKNOWN')]]:
        with pytest.raises(ValueError):
            predict(invalid,test,labels,KINDS[0])
    with pytest.raises(ValueError,match='Known binary'):
        predict(cal,test,{},KINDS[0])
    with pytest.raises(ValueError):
        predict(cal,test+test,labels,KINDS[0])
