from copy import deepcopy
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import causal_shadow_bundle as shadow
from predictive_portfolio_research import fit_predict
from split_context_audit import normalized_opening_rows


def test_fitted_head_exactly_matches_original_classifier_calibration():
    rng=np.random.default_rng(19)
    rows=[dict(date=f'{i:04}',symbol='AAPL',features=rng.normal(size=16).tolist()) for i in range(90)]
    labels={(r['date'],r['symbol']):i%2 for i,r in enumerate(rows)}
    train,cal,test=rows[:50],rows[50:80],rows[80:]
    expected=fit_predict(train,cal,test,'logistic',labels)
    head=shadow.fit_head(train,cal,labels)
    assert shadow.predict_head(head,test)==expected.tolist()
    labels.update({(r['date'],r['symbol']):1-labels[(r['date'],r['symbol'])] for r in test})
    assert shadow.predict_head(shadow.fit_head(train,cal,labels),test)==expected.tolist()
    with pytest.raises(ValueError): shadow.fit_head(cal,train,labels)


def observations(monkeypatch):
    monkeypatch.setattr(shadow,'SYMBOLS',['AAPL','MSFT'])
    dates=pd.bdate_range(end='2026-10-09',periods=25).strftime('%Y-%m-%d').tolist()
    def frame(minutes,price):
        return pd.DataFrame(dict(minute=minutes,open=price,high=price+.2,low=price-.2,close=price,volume=1000.))
    data={s:{d:frame(list(range(570,600))+[959],100+i*.01) for i,d in enumerate(dates)} for s in shadow.SYMBOLS}
    for s in data: data[s]['2026-10-12']=frame(list(range(570,600)),100.25)
    return data


def test_opening_rows_match_research_builder_without_future_closing_bar(monkeypatch):
    data=observations(monkeypatch)
    expected,_,_=normalized_opening_rows(data,[])
    rows,quality=shadow.opening_inputs(data,[],'2026-10-12')
    assert rows==[expected['2026-10-12'][s] for s in sorted(expected['2026-10-12'])]
    assert len(rows)==2 and all(len(r['features'])==16 for r in rows)
    assert quality['candidate_symbols']==['AAPL','MSFT']


def test_current_future_and_incomplete_packets_rejected(monkeypatch):
    data=observations(monkeypatch)
    later=deepcopy(data);later['AAPL']['2026-10-13']=later['AAPL']['2026-10-12']
    with pytest.raises(ValueError): shadow.opening_inputs(later,[],'2026-10-12')
    later=deepcopy(data);later['AAPL']['2026-10-12'].loc[30]=[600,100,101,99,100,1000]
    with pytest.raises(ValueError): shadow.opening_inputs(later,[],'2026-10-12')
    missing=deepcopy(data);missing['AAPL']['2026-10-12']=missing['AAPL']['2026-10-12'].iloc[:-1]
    with pytest.raises(ValueError): shadow.opening_inputs(missing,[],'2026-10-12')
    invalid=deepcopy(data);invalid['AAPL']['2026-10-12'].loc[0,'high']=90
    with pytest.raises(ValueError): shadow.opening_inputs(invalid,[],'2026-10-12')
    stale=deepcopy(data)
    for days in stale.values(): days['2026-10-19']=days.pop('2026-10-12')
    with pytest.raises(ValueError): shadow.opening_inputs(stale,[],'2026-10-19')


def test_future_split_does_not_change_current_inputs(monkeypatch):
    data=observations(monkeypatch)
    before,_=shadow.opening_inputs(data,[],'2026-10-12')
    future=[dict(symbol='AAPL',ex_date='2026-10-13',ratio=10.,id='future')]
    after,_=shadow.opening_inputs(data,future,'2026-10-12')
    assert before==after


def test_freezer_never_overwrites_existing_experiment(tmp_path):
    with pytest.raises(ValueError):
        shadow.freeze_bundle(Path('missing'),tmp_path,Path('missing'),Path('missing'),'2026-10-12')
    assert list(tmp_path.iterdir())==[]


def test_hash_is_checked_before_deserializing(monkeypatch,tmp_path):
    monkeypatch.setattr(shadow.evidence,'read_manifest',lambda d:dict(manifest=dict(artifact_sha256='expected')))
    monkeypatch.setattr(shadow.evidence,'file_digest',lambda p:'wrong')
    def forbidden(*args,**kwargs): raise AssertionError('Unverified artifact was deserialized')
    monkeypatch.setattr(shadow.joblib,'load',forbidden)
    with pytest.raises(ValueError): shadow.load_own_bundle(tmp_path)
