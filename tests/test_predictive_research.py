from copy import deepcopy
import numpy as np
import pandas as pd
import pytest
from predictive_research import (example, split, fit, probability, evaluate, wilson,
                                opening_features, shadow_probability, FEATURES)


def market():
    dates=pd.date_range('2026-01-05 09:30',periods=390,freq='min',tz='America/New_York')
    bars=pd.DataFrame(dict(open=100.,high=100.2,low=99.8,close=100.,volume=1000.),index=dates)
    history=[dict(close=99+i*.01,opening_volume=5000.) for i in range(21)]
    return bars,history


def test_future_prices_cannot_change_features():
    bars,history=market()
    original=example('2026-01-05',bars,history)
    changed=bars.copy()
    changed.iloc[10:,changed.columns.get_loc('close')]=110
    changed.iloc[10:,changed.columns.get_loc('low')]=90
    other=example('2026-01-05',changed,history)
    assert original['features']==other['features']
    assert original['label'] != other['label'] or original['net_return'] != other['net_return']


def test_gap_above_completed_signal_not_assumed_filled():
    bars,history=market()
    bars.iloc[6,bars.columns.get_loc('open')]=101
    assert not example('2026-01-05',bars,history)['filled']


def test_stop_gap_uses_worse_opening_price():
    bars,history=market()
    bars.iloc[10,bars.columns.get_loc('open')]=97
    bars.iloc[10,bars.columns.get_loc('low')]=96
    row=example('2026-01-05',bars,history)
    assert row['exit_reason']=='stop'
    assert row['exit']==pytest.approx(97*.999)


def test_holdout_dates_are_strictly_separated():
    records=[dict(date=f'{i:04d}') for i in range(300)]
    train,cal,test=split(records)
    assert train[-1]['date'] < cal[0]['date'] < cal[-1]['date'] < test[0]['date']
    assert len(test)==60


def test_small_dataset_rejected():
    with pytest.raises(ValueError): split([{}]*100)


def rows(n=300):
    return [dict(date=f'{i:04d}',features=[i/100,j:=i%2,0,0,0,0,0,0],
        label=j,filled=True,entry=100.1,limit=100.1,stop=99.,
        exit=101. if j else 99.,exit_reason='session') for i in range(n)]


def test_test_labels_do_not_affect_fitting_or_predictions():
    train,cal,test=split(rows())
    model,calibrator=fit(train,cal,'logistic')
    p=probability(model,calibrator,test)
    changed=deepcopy(test)
    for r in changed: r['label']=1-r['label']
    assert np.array_equal(p,probability(model,calibrator,changed))
    assert model[0].mean_[0]==pytest.approx(np.mean([r['features'][0] for r in train]))


def test_no_trades_not_counted_as_winning_days():
    report=evaluate(rows(20),np.zeros(20),.9)
    assert report['active_days']==0 and report['no_trade_days']==20
    assert report['win_rate_pct'] is None and not report['target_demonstrated']


def test_high_hit_rate_without_sample_not_certified():
    assert wilson(9,10)[0]<90
    assert wilson(90,100)[0]<90


def test_stop_sizing_includes_both_side_friction():
    row=rows(1)[0]
    report=evaluate([row],[1],.9)
    trade=report['trades'][0]
    assert trade['qty']*row['limit']<=5000
    assert trade['qty']*(row['entry']-row['stop']*.999)<=50


def test_shadow_inference_has_no_order_authority():
    train,cal,test=split(rows())
    model,calibrator=fit(train,cal,'logistic')
    bars,history=market()
    result=shadow_probability(dict(model=model,calibrator=calibrator,
        mode='shadow_only',features=FEATURES),bars.iloc[:5],history)
    assert 0 <= result['probability'] <= 1
    assert not result['broker_orders_enabled'] and not result['validated_for_production']


def test_live_feature_input_rejects_uncompleted_opening_or_missing_history():
    bars,history=market()
    with pytest.raises(ValueError): opening_features(bars.iloc[:4],history)
    with pytest.raises(ValueError): opening_features(bars.iloc[:5],history[:20])
