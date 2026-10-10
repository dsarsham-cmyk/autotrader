import json
import numpy as np
import pandas as pd
import pytest
import iex_bar_predictive_research as research


def frame(date,symbol):
    times=list(pd.date_range(date+' 09:30',periods=30,freq='min',tz='America/New_York'))
    times+=list(pd.date_range(date+' 15:55',periods=5,freq='min',tz='America/New_York'))
    return pd.DataFrame(dict(symbol=symbol,timestamp=[t.isoformat() for t in times],
        open=100.,high=101.,low=99.,close=100.,volume=1000.))


def fixture():
    dates=pd.bdate_range('2026-08-03',periods=26).strftime('%Y-%m-%d').tolist()
    observations={s:{d:research.proxy_sessions(frame(d,s),s)[d] for d in dates} for s in ['A','B']}
    bars=np.tile([100.,101.,99.,100.,1000.],(390,1))
    sip={d:{s:(bars.copy(),{}) for s in ['A','B']} for d in dates}
    return dates,observations,sip


def test_sip_prices_and_volumes_cannot_enter_any_iex_features():
    dates,observations,sip=fixture();before,_=research.matched_rows(sip,observations)
    for stocks in sip.values():
        for a,_ in stocks.values(): a[:]=[200,210,190,200,1e9]
    after,_=research.matched_rows(sip,observations)
    assert before==after and len(after[-1]['features'])==16


def test_iex_todays_future_close_or_absence_cannot_change_today_signal():
    dates,observations,sip=fixture();before,_=research.matched_rows(sip,observations)
    for s in observations:
        regular=observations[s][dates[-1]]
        observations[s][dates[-1]]=regular.loc[regular.minute<600].copy()
    after,_=research.matched_rows(sip,observations)
    assert before==after


def test_iex_market_features_do_not_use_future_sip_completeness():
    dates,observations,sip=fixture();before,_=research.matched_rows(sip,observations)
    del sip[dates[-1]]['B']
    after,_=research.matched_rows(sip,observations)
    old=[r for r in before if r['date']==dates[-1] and r['symbol']=='A'][0]
    new=[r for r in after if r['date']==dates[-1] and r['symbol']=='A'][0]
    assert old==new


@pytest.mark.parametrize('issue',['sparse','stale'])
def test_sparse_stale_current_iex_signal_abstains_and_keeps_day(issue):
    dates,observations,sip=fixture()
    regular=observations['A'][dates[-1]]
    observations['A'][dates[-1]]=regular.loc[regular.minute>=590].copy() if issue=='sparse' else regular.loc[regular.minute!=599].copy()
    rows,_=research.matched_rows(sip,observations)
    a=[r for r in rows if r['date']==dates[-1] and r['symbol']=='A'][0]
    assert not a['predecision_eligible'] and a['eligibility_reason']=='sparse_or_stale_iex_opening'


def test_loader_rejects_sip_metadata_instead_of_reusing_its_model(tmp_path):
    path=tmp_path/'AAPL.csv';path.write_text('not_read_if_wrong_feed')
    path.with_suffix('.metadata.json').write_text(json.dumps(dict(feed='sip',adjustment='raw',sha256=research.hash_file(path))))
    with pytest.raises(ValueError,match='no SIP substitution'): research.load_iex(tmp_path)


@pytest.mark.parametrize('kind',['logistic','mlp','quantum_fidelity'])
def test_each_timing_policy_refits_its_past_outcomes_without_future_fill_selection(monkeypatch,kind):
    rows=[dict(date=f'{i:04d}',symbol='A',features=[1],signal_price=100,predecision_eligible=True) for i in range(261)]
    a=np.tile([100.,100.2,99.8,100.,1000.],(390,1))
    sip={r['date']:{'A':(a.copy(),{})} for r in rows}
    sip['0001']['A'][0][35,1]=101  # fresh policy wins, delayed policy misses it
    sip['0260']['A'][0][31]=[102,103,101,102,1000]
    seen=[]
    def fit(train,cal,test,kind,labels):
        assert max(r['date'] for r in train)<min(r['date'] for r in cal)
        assert max(r['date'] for r in cal)<min(r['date'] for r in test)
        seen.append(labels[('0001','A')]);return np.full(len(test),.7)
    monkeypatch.setattr(research,'fit_predict',fit)
    monkeypatch.setattr(research,'fit_neural',lambda tr,ca,te,la:(fit(tr,ca,te,'mlp',la),{}))
    monkeypatch.setattr(research,'fit_quantum',lambda tr,ca,te,la,ki:fit(tr,ca,te,ki,la))
    fresh,_=research.walk(rows,sip,kind,1);delayed,_=research.walk(rows,sip,kind,16)
    assert len(fresh)==len(delayed)==21 and seen==[1,1,0,0]
