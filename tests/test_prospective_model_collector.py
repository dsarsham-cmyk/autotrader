from datetime import datetime,timedelta,timezone
from pathlib import Path
import ast
import numpy as np
import pytest
import prospective_model_collector as collector
import prospective_forecast_evidence as evidence
from regime_predictive_research import extended_rows


def context():
    start=datetime(2026,8,1)
    prior={str((start+timedelta(days=i)).date()):{
        s:(np.tile([100.,101,99,100,1000],(390,1)),
           dict(relative_volume=1,prior_dollars=39e6)) for s in collector.SYMBOLS}
        for i in range(25)}
    current={s:np.tile([100.,101,99,100,1000],(30,1)) for s in collector.SYMBOLS}
    return prior,current,'2026-09-01'


def test_partial_opening_matches_offline_features_without_current_day_close():
    prior,current,date=context()
    actual=collector.current_context(prior,current,date)
    complete={**prior,date:{s:(np.tile([100.,101,99,100,1000],(390,1)),
        dict(relative_volume=1,prior_dollars=39e6)) for s in collector.SYMBOLS}}
    expected=[r for r in extended_rows(complete) if r['date']==date]
    assert len(actual)==20
    for a,b in zip(actual,expected): assert np.allclose(a['features'],b['features'])


def test_future_history_and_incomplete_current_universe_rejected():
    prior,current,date=context()
    with pytest.raises(ValueError): collector.current_context(prior,current,'2026-08-10')
    del current['AAPL']
    with pytest.raises(ValueError): collector.current_context(prior,current,date)


def test_invalid_ohlc_rejected():
    prior,current,date=context()
    current['AAPL'][0,1]=50
    with pytest.raises(ValueError): collector.current_context(prior,current,date)


def test_outside_window_never_calls_api_or_deserializes_model(tmp_path,monkeypatch):
    artifact=tmp_path/'model.joblib';artifact.write_bytes(b'not executable model')
    source=tmp_path/'source';source.write_text('source')
    monkeypatch.setattr(evidence,'utc_now',lambda:datetime(2026,10,10,14,tzinfo=timezone.utc))
    evidence.freeze(tmp_path,artifact,[source],'2026-10-01','2026-10-12')
    monkeypatch.setattr(collector,'get_json',lambda *a:pytest.fail('No API calls allowed outside window'))
    monkeypatch.setattr(collector.joblib,'load',lambda *a:pytest.fail('Do not deserialize outside window'))
    with pytest.raises(ValueError,match='Outside'):
        collector.collect(tmp_path,tmp_path/'history')


def test_no_order_clients_or_http_write_methods():
    tree=ast.parse(Path('prospective_model_collector.py').read_text())
    modules=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert not any(m and (m.startswith('alpaca.trading') or m in {'broker','safe_paper_engine'}) for m in modules)
    methods=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
    assert not any(method in {'post','put','patch','delete','submit_order'} for method in methods)
