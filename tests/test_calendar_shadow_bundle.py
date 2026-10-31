"""Synthetic fixtures are not real prospective observations or trading evidence."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
import calendar_shadow_bundle as shadow


def inputs(monkeypatch):
    monkeypatch.setattr(shadow, 'SYMBOLS', ['AAPL', 'MSFT'])
    dates = pd.bdate_range(end='2026-10-30', periods=25).strftime('%Y-%m-%d').tolist()
    def frame(minutes, price):
        return pd.DataFrame(dict(minute=minutes, open=price, high=price+.2,
                                 low=price-.2, close=price, volume=1000.))
    observations = {s: {d: frame(list(range(570, 600))+[779 if d == dates[-1] else 959], 100+i*.01)
                       for i, d in enumerate(dates)} for s in shadow.SYMBOLS}
    for days in observations.values():
        days['2026-11-02'] = frame(list(range(570, 600)), 100.25)
    calendar = [dict(date=d, open='09:30', close='13:00' if d == dates[-1] else '16:00')
                for d in dates+['2026-11-02']]
    return observations, calendar


def test_half_day_prior_close_and_after_hours_do_not_pollute_inputs(monkeypatch):
    data, calendar = inputs(monkeypatch)
    before, quality = shadow.opening_inputs(data, [], calendar, '2026-11-02')
    assert len(before) == 2 and all(len(r['features']) == 16 for r in before)
    assert all(r['features'][13] == 0 for r in before)
    changed = deepcopy(data)
    for days in changed.values():
        days['2026-10-30'].loc[31] = [959, 999, 1000, 998, 999, 999999]
    after, other_quality = shadow.opening_inputs(changed, [], calendar, '2026-11-02')
    assert before == after and quality == other_quality


@pytest.mark.parametrize('corruption', ['current_missing', 'current_later', 'future_history',
    'prior_close_missing', 'invalid_ohlc', 'duplicate_minute', 'future_calendar', 'missing_calendar', 'future_split'])
def test_corrupt_or_future_information_rejected(monkeypatch, corruption):
    data, calendar = inputs(monkeypatch); events = []
    if corruption == 'current_missing':
        data['AAPL']['2026-11-02'] = data['AAPL']['2026-11-02'].iloc[:-1]
    elif corruption == 'current_later':
        data['AAPL']['2026-11-02'].loc[30] = [600, 100, 101, 99, 100, 1000]
    elif corruption == 'future_history':
        data['AAPL']['2026-11-03'] = data['AAPL']['2026-11-02']
    elif corruption == 'prior_close_missing':
        data['AAPL']['2026-10-30'] = data['AAPL']['2026-10-30'].iloc[:-1]
    elif corruption == 'invalid_ohlc':
        data['AAPL']['2026-11-02'].loc[0, 'high'] = 1
    elif corruption == 'duplicate_minute':
        data['AAPL']['2026-10-30'].loc[30, 'minute'] = 570
    elif corruption == 'future_calendar':
        calendar.append(dict(date='2026-11-03', open='09:30', close='16:00'))
    elif corruption == 'missing_calendar':
        calendar.pop(0)
    elif corruption == 'future_split':
        events = [dict(symbol='AAPL', ex_date='2026-11-03', ratio=10.)]
    with pytest.raises(ValueError):
        shadow.opening_inputs(data, events, calendar, '2026-11-02')


def test_hash_and_source_closure_checked_before_deserialization(monkeypatch, tmp_path):
    monkeypatch.setattr(shadow.evidence, 'read_manifest', lambda d: {'manifest': {
        'source_sha256': {s: 'wrong' for s in shadow.source_closure()}, 'artifact_sha256': 'wrong'}})
    monkeypatch.setattr(shadow.joblib, 'load', lambda *a: pytest.fail('Unverified pickle loaded'))
    with pytest.raises(ValueError):
        shadow.load_own_bundle(tmp_path)


def test_fit_and_own_frozen_roundtrip(monkeypatch, tmp_path):
    data, calendar = inputs(monkeypatch)
    rng = np.random.default_rng(19)
    dates = pd.bdate_range(end='2026-10-01', periods=90).strftime('%Y-%m-%d').tolist()
    rows = [dict(date=d, symbol='AAPL', features=rng.normal(size=16).tolist(), signal_price=100+i%2)
            for i, d in enumerate(dates)]
    monkeypatch.setattr(shadow, 'path', lambda market, signal_price, **kw: {
        'filled': True, 'label': int(signal_price == 101)})
    heads, counts, observed = shadow.fit_heads(rows, {})
    assert observed == dates and all(c['calibration_rows'] == 60 for c in counts.values())
    bundle = dict(schema=1, mode=shadow.MODE, heads=heads, orders=False, production_approved=False,
        independent_validation_pass=False, prior_exploration_failed_target=True,
        trained_through='2026-10-01', features=shadow.FEATURES, symbols=list(shadow.SYMBOLS),
        runtime_lock=shadow.runtime_lock())
    joblib.dump(bundle, tmp_path/'model.joblib')
    monkeypatch.setattr(shadow.evidence, 'utc_now', lambda: datetime(2026, 10, 31, tzinfo=timezone.utc))
    shadow.evidence.freeze(tmp_path, tmp_path/'model.joblib', shadow.source_closure(),
        '2026-10-01', '2026-11-02', source_root=Path.cwd(), history_provenance_required=True)
    result = shadow.infer(tmp_path, data, [], calendar, '2026-11-02')
    assert len(result['predictions']) == 2
    assert not result['orders'] and not result['independent_validation_pass']
    for row in result['predictions']:
        assert set(row['probabilities']) == set(shadow.TARGETS)
        assert all(0 <= p <= 1 for p in row['probabilities'].values())
    bundle['runtime_lock']['python'] = 'incompatible'
    joblib.dump(bundle, tmp_path/'model.joblib')
    # Artifact mutation is rejected even before inspecting incompatible runtime.
    with pytest.raises(ValueError):
        shadow.load_own_bundle(tmp_path)


def test_freeze_never_overwrites_or_starts_in_the_past(tmp_path):
    with pytest.raises(ValueError):
        shadow.freeze_bundle(Path('missing'), tmp_path, Path('missing'), Path('missing'), Path('missing'))
    assert list(tmp_path.iterdir()) == []


def test_source_closure_contains_calendar_and_frozen_classifier_dependencies():
    closure = shadow.source_closure()
    assert {'calendar_shadow_bundle.py', 'calendar_regular_context.py', 'causal_shadow_bundle.py',
            'macro_context_research.py', 'balanced_target_simulator.py', 'prospective_forecast_evidence.py'} <= set(closure)
