import numpy as np
import pandas as pd
import pytest
import premarket_predictive_research as research


def frame(date='2026-10-01'):
    times=pd.date_range(f'{date} 08:00',periods=95,freq='min',tz='America/New_York')
    return pd.DataFrame(dict(symbol='A',timestamp=[t.isoformat() for t in times],
        open=100.,high=101.,low=99.,close=100.,volume=1000.))


@pytest.mark.parametrize('date',['2026-10-01','2026-01-02'])
def test_dst_exact_cutoff_and_post_cutoff_mutation_cannot_change_window(date):
    source=frame(date);before=research.windows(source,'A')[date]
    source.loc[90:,['open','high','low','close','volume']]=[200,210,190,200,1e9]
    after=research.windows(source,'A')[date]
    pd.testing.assert_frame_equal(before,after)
    assert len(after)==90 and after.minute.iloc[-1]==569


def test_relative_premarket_volume_uses_only_past_window_volumes():
    w=research.windows(frame(),'A')['2026-10-01'];a=np.tile([100,101,99,100,1000.],(390,1))
    values,reason=research.context(w,[90000.]*20,a)
    assert reason=='eligible' and values[5]==pytest.approx(np.log(2))
    changed,_=research.context(w,[180000.]*20,a)
    assert changed[5]==pytest.approx(np.log(1.5))
    assert values[:5]==changed[:5] and values[6:]==changed[6:]


def test_missing_sparse_or_stale_context_abstains_not_fallback():
    a=np.tile([100,101,99,100,1000.],(390,1));w=research.windows(frame(),'A')['2026-10-01']
    assert research.context(None,[1]*20,a)[0] is None
    assert research.context(w.iloc[:30],[1]*20,a)[1]=='sparse_or_stale_window'
    assert research.context(w,[1]*19,a)[1]=='insufficient_prior_window_history'
    assert research.context(w,[0]*20,a)[1]=='zero_volume_context'


@pytest.mark.parametrize('issue',['naive','duplicate','future_window'])
def test_ambiguous_sources_and_future_context_fail_closed(issue):
    source=frame()
    if issue=='naive': source.timestamp=source.timestamp.str.slice(0,19)
    if issue=='duplicate': source.loc[1,'timestamp']=source.loc[0,'timestamp']
    if issue=='future_window':
        w=research.windows(source,'A')['2026-10-01'];w.loc[89,'minute']=570
        with pytest.raises(ValueError): research.context(w,[1]*20,np.ones((390,5)))
        return
    with pytest.raises(ValueError): research.windows(source,'A')


def test_ineligible_test_day_is_retained_and_unknown_fill_never_prefilters(monkeypatch):
    rows=[dict(date=f'{i:04d}',symbol='A',features=[1],signal_price=100,
        predecision_eligible=i!=260) for i in range(261)]
    bars=np.tile([100.,100.2,99.8,100.,1000.],(390,1))
    data={r['date']:{'A':(bars.copy(),{})} for r in rows}
    data['0259']['A'][0][46]=[102,103,101,102,1000]
    seen=[]
    def fit(train,cal,test,kind,labels):
        assert all(r['predecision_eligible'] for r in train+cal+test)
        assert max(r['date'] for r in cal)<min(r['date'] for r in test)
        seen.extend(r['date'] for r in test)
        return np.full(len(test),.7)
    monkeypatch.setattr(research,'fit_predict',fit)
    predictions,_=research.walk(rows,data,'logistic')
    assert len(predictions)==21 and '0259' in seen and '0260' not in seen
    assert predictions[-1]['probability']==0 and not predictions[-1]['probability_is_forecast']


def test_future_label_mutation_cannot_change_classical_predictions(monkeypatch):
    rows=[dict(date=f'{i:04d}',symbol='A',features=[1],signal_price=100,
        predecision_eligible=True) for i in range(261)]
    bars=np.tile([100.,100.2,99.8,100.,1000.],(390,1))
    data={r['date']:{'A':(bars.copy(),{})} for r in rows}
    def fit(train,cal,test,kind,labels):
        return np.full(len(test),np.mean([labels[(r['date'],r['symbol'])] for r in train+cal]))
    monkeypatch.setattr(research,'fit_predict',fit)
    before,_=research.walk(rows,data,'boosted')
    data['0260']['A'][0][60,1]=101
    after,_=research.walk(rows,data,'boosted')
    assert before==after


def integration_data():
    dates=pd.bdate_range('2026-08-03',periods=26).strftime('%Y-%m-%d').tolist()
    bars=np.tile([100.,101.,99.,100.,1000.],(390,1))
    source={d:{'A':(bars.copy(),dict(prior_dollars=3e7,relative_volume=1))} for d in dates}
    observations={'A':{d:research.windows(frame(d),'A')[d] for d in dates}}
    return dates,source,observations


def test_integrated_current_features_ignore_post_opening_cutoff_outcomes():
    dates,source,observations=integration_data()
    before,_=research.matched_rows(source,observations)
    source[dates[-1]]['A'][0][30:]=[200,210,190,200,1e9]
    after,_=research.matched_rows(source,observations)
    assert before==after and len(after[-1]['features'])==31


def test_missing_current_window_retains_session_and_does_not_change_earlier_rows():
    dates,source,observations=integration_data()
    before,_=research.matched_rows(source,observations)
    del observations['A'][dates[-1]]
    after,_=research.matched_rows(source,observations)
    assert before[:-1]==after[:-1] and len(before)==len(after)
    assert not after[-1]['predecision_eligible'] and after[-1]['eligibility_reason']=='missing_window'
