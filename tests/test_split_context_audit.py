from copy import deepcopy

import pytest

from causal_opening_inventory import FEATURES, opening_rows
from split_context_audit import events_from_pages, inspect, normalized_opening_rows
from tests.test_iex_bar_predictive_research import fixture


def event(date, ratio=10):
    return dict(symbol='A', ex_date=date, ratio=ratio, id='one', kind='forward_splits', process_date=date)


def split_fixture():
    dates, observations, _ = fixture()
    effective = dates[-3]
    for date, frame in observations['A'].items():
        if date >= effective:
            frame[['open','high','low','close']] /= 10
            frame['volume'] *= 10
    return dates, observations, event(effective)


def test_empty_event_control_reproduces_exact_original():
    _, observations, _ = fixture()
    original, reasons = opening_rows(observations)
    control, control_reasons, applications = normalized_opening_rows(observations, [])
    assert original == control and reasons == control_reasons and not applications


def test_split_corrects_gap_and_volume_without_backdating_or_mutation():
    dates, observations, change = split_fixture()
    saved = deepcopy(observations)
    original, _ = opening_rows(observations)
    normalized, _, applied = normalized_opening_rows(observations, [change])
    previous = dates[-4]
    assert original[previous] == normalized[previous]
    raw = original[change['ex_date']]['A']
    corrected = normalized[change['ex_date']]['A']
    assert raw['features'][FEATURES.index('gap')] == pytest.approx(-.9)
    assert corrected['features'][FEATURES.index('gap')] == pytest.approx(0)
    _, unit_reference, _ = fixture()
    reference, _ = opening_rows(unit_reference)
    assert corrected['features'] == pytest.approx(reference[change['ex_date']]['A']['features'])
    assert raw['signal_price'] == corrected['signal_price'] == 10
    assert applied[0]['effective_date'] == applied[0]['applied_before_session']
    for symbol in observations:
        for date in observations[symbol]:
            assert observations[symbol][date].equals(saved[symbol][date])


def test_future_event_and_future_close_cannot_change_current_signal():
    dates, observations, _ = fixture()
    original, _ = opening_rows(observations)
    normalized, _, applications = normalized_opening_rows(observations, [event('2027-01-01')])
    assert normalized == original and not applications
    before, _, _ = normalized_opening_rows(observations, [event(dates[-1])])
    observations['A'][dates[-1]] = observations['A'][dates[-1]].loc[lambda a:a.minute<600]
    after, _, _ = normalized_opening_rows(observations, [event(dates[-1])])
    assert before == after


def test_missing_effective_session_applies_once_on_next_observed_date():
    dates, observations, change = split_fixture()
    del observations['A'][change['ex_date']]
    normalized, _, applications = normalized_opening_rows(observations, [change])
    assert len(applications) == 1 and applications[0]['applied_before_session'] == dates[-2]
    assert normalized[dates[-2]]['A']['features'][FEATURES.index('gap')] == pytest.approx(0)


def test_reverse_split_rescales_prices_and_volume_in_opposite_direction():
    dates, observations, _ = fixture()
    for date, frame in observations['A'].items():
        if date >= dates[-1]:
            frame[['open','high','low','close']] *= 5
            frame['volume'] /= 5
    normalized, _, _ = normalized_opening_rows(observations, [event(dates[-1], .2)])
    _, reference, _ = fixture()
    rows, _ = opening_rows(reference)
    assert normalized[dates[-1]]['A']['features'] == pytest.approx(rows[dates[-1]]['A']['features'])
    assert normalized[dates[-1]]['A']['signal_price'] == 500


def test_parser_rejects_conflicting_events_invalid_rates_and_dates():
    record = dict(symbol='A',ex_date='2026-09-01',process_date='2026-09-01',id='one',old_rate=1,new_rate=10)
    page = dict(corporate_actions=dict(forward_splits=[record]))
    assert events_from_pages([page],['A'])[0]['ratio'] == 10
    for key,value in [('old_rate',0),('new_rate',float('nan')),('new_rate',True),
                      ('new_rate',.5),('symbol','B'),('ex_date','2026-9-1')]:
        bad = deepcopy(page)
        bad['corporate_actions']['forward_splits'][0][key] = value
        with pytest.raises(ValueError):
            events_from_pages([bad],['A'])
    with pytest.raises(ValueError,match='Duplicate'):
        events_from_pages([page,page],['A'])


def test_input_audit_never_claims_profit_or_approval():
    _, observations, change = split_fixture()
    report = inspect(observations,[change])
    assert report['changed_rows'] == 3
    assert report['eligibility_unchanged'] and report['raw_signal_prices_unchanged']
    for key in ['orders','production_approved','independent_validation_pass',
                'performance_screen_pass','economic_evaluation_performed']:
        assert report[key] is False
