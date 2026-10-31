from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from research_clock import ClockSkewError, validate_sample, verify_remote_clock, require_fresh

START = datetime(2026, 10, 31, 16, 0, 0, 200000, tzinfo=timezone.utc)
DATE = 'Sat, 31 Oct 2026 16:00:00 GMT'


def sample(**kwargs):
    values = dict(date_header=DATE, local_started=START,
                  local_received=START+timedelta(seconds=.1),
                  monotonic_started=100., monotonic_received=100.1)
    values.update(kwargs)
    return validate_sample(**values)


def test_fast_consistent_request_does_not_adjust_time():
    value = sample()
    assert value['checked_utc'] == (START+timedelta(seconds=.1)).isoformat()
    assert value['timestamp_adjusted'] is False
    assert value['independent_timestamp_anchor'] is False


@pytest.mark.parametrize('offset', [21, -21, 3, -3])
def test_skew_is_blocked_not_corrected(offset):
    with pytest.raises(ClockSkewError):
        sample(local_started=START+timedelta(seconds=offset),
               local_received=START+timedelta(seconds=offset+.1))


@pytest.mark.parametrize('date', [None, '', 'garbage', '2026-10-31T16:00:00Z',
    'Sat, 31 Oct 2026 15:58:00 GMT', DATE+', '+DATE])
def test_missing_stale_or_noncanonical_date_rejected(date):
    with pytest.raises(ClockSkewError):
        sample(date_header=date)


@pytest.mark.parametrize('change', [
    {'monotonic_received': 102., 'local_received': START+timedelta(seconds=2)},
    {'monotonic_received': 99.}, {'monotonic_received': float('nan')},
    {'local_received': START+timedelta(seconds=1)},
    {'local_started': START.replace(tzinfo=None)},
    {'local_received': START.replace(tzinfo=None)}, {'age_header': '1'},
    {'age_header': 'invalid'}, {'tolerance': 21}, {'max_rtt': 30}])
def test_bad_timing_cache_or_relaxed_policy_fails_closed(change):
    with pytest.raises(ClockSkewError):
        sample(**change)


def test_nonce_no_cache_tls_and_redirect_policy():
    urls = []
    def get(url, **kwargs):
        urls.append(url)
        assert kwargs['verify'] is True and kwargs['allow_redirects'] is False
        assert 'no-cache' in kwargs['headers']['Cache-Control']
        assert 'Authorization' not in kwargs['headers']
        return SimpleNamespace(status_code=200, url=url, history=[], headers={'Date': DATE, 'Age': '0'})
    def probe():
        walls = iter([START, START+timedelta(seconds=.1)])
        monos = iter([100., 100.1])
        return verify_remote_clock(lambda: next(walls), lambda: next(monos), get)
    assert probe()['status'] == 'wall_clock_consistent_not_absolute_utc_proof'
    assert probe()['status'] == 'wall_clock_consistent_not_absolute_utc_proof'
    assert urls[0] != urls[1]


@pytest.mark.parametrize('variant', ['redirect', 'cached', 'bad_status', 'exception'])
def test_remote_failures_rejected(variant):
    def get(url, **kwargs):
        if variant == 'exception':
            raise TimeoutError('do not expose tokens or provider errors')
        return SimpleNamespace(status_code=403 if variant == 'bad_status' else 200,
            url=url+'redirect' if variant == 'redirect' else url, history=[],
            headers={'Date': DATE, 'X-Cache': 'HIT' if variant == 'cached' else 'MISS'})
    walls = iter([START, START+timedelta(seconds=.1)]); monos = iter([100., 100.1])
    with pytest.raises(ClockSkewError):
        verify_remote_clock(lambda: next(walls), lambda: next(monos), get)


def test_checked_sample_expires_and_no_monotonic_time_travel():
    value = sample()
    assert require_fresh(value, lambda: 101.) is value
    for current in [99., 106., float('nan')]:
        with pytest.raises(ClockSkewError):
            require_fresh(value, lambda: current)
