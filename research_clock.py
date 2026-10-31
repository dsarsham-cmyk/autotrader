"""Fail-closed research wall-clock consistency check. Never adjust timestamps.

HTTP Date is an approximation of response origination, not an NTP service or
an authenticated observation timestamp (RFC9110 sections5.6.7/6.6.1).
Intervals assume the TLS endpoint's clock is accurate within its whole-second
representation. This guard rejects skew; it does not prove absolute UTC time.
"""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime, format_datetime
import math
import secrets
import time

URL = 'https://api.github.com/rate_limit'


class ClockSkewError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def validate_sample(date_header, local_started, local_received, monotonic_started,
                    monotonic_received, age_header=None, max_rtt=1.0, tolerance=1.0):
    """Pure comparison. Allowed tolerance is deliberately bounded, not a bypass."""
    if (not 0 < max_rtt <= 1 or not 0 <= tolerance <= 1
            or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v)
                   for v in (monotonic_started, monotonic_received))):
        raise ClockSkewError('Invalid clock guard bounds')
    if any(not isinstance(t, datetime) or t.tzinfo is None for t in (local_started, local_received)):
        raise ClockSkewError('Aware local UTC clocks required')
    rtt = monotonic_received-monotonic_started
    if not 0 <= rtt <= max_rtt:
        raise ClockSkewError('Clock probe RTT unavailable or too large')
    wall_elapsed = (local_received-local_started).total_seconds()
    if abs(wall_elapsed-rtt) > .05:
        raise ClockSkewError('Wall clock changed during probe')
    if age_header is not None and str(age_header).strip() != '0':
        raise ClockSkewError('Cached clock response forbidden')
    try:
        remote = parsedate_to_datetime(date_header)
        if remote.tzinfo is None or format_datetime(remote, usegmt=True) != date_header:
            raise ValueError('Canonical GMT Date required')
    except (TypeError, ValueError, OverflowError):
        raise ClockSkewError('Missing or invalid remote HTTP Date') from None
    # One second representation uncertainty on either side, plus the full RTT
    # on the upper side: no assumption of symmetric network latency.
    lower = remote-timedelta(seconds=1)
    upper = remote+timedelta(seconds=1+rtt)
    if not lower-timedelta(seconds=tolerance) <= local_received <= upper+timedelta(seconds=tolerance):
        raise ClockSkewError('Local wall clock inconsistent with fresh remote Date')
    return dict(status='wall_clock_consistent_not_absolute_utc_proof',
        checked_utc=local_received.astimezone(timezone.utc).isoformat(),
        remote_date_utc=remote.isoformat(), rtt_seconds=rtt,
        assumed_remote_interval_lower_utc=lower.isoformat(),
        assumed_remote_interval_upper_utc=upper.isoformat(),
        tolerance_seconds=tolerance, received_monotonic=monotonic_received,
        orders=False, timestamp_adjusted=False, independent_timestamp_anchor=False)


def verify_remote_clock(wall_clock=utc_now, monotonic=time.monotonic, get=None):
    """One unauthenticated GET, random cache-buster, TLS on, no redirects/retry."""
    if get is None:
        import requests
        get = requests.get
    nonce = secrets.token_hex(32)
    url = URL+'?research_clock_nonce='+nonce
    local_started = wall_clock(); monotonic_started = monotonic()
    try:
        response = get(url, headers={'Cache-Control': 'no-cache, no-store',
            'Pragma': 'no-cache', 'Accept': 'application/vnd.github+json'},
            timeout=2, allow_redirects=False, verify=True)
        monotonic_received = monotonic(); local_received = wall_clock()
        if response.status_code != 200 or response.url != url or getattr(response, 'history', []):
            raise ClockSkewError('Unsupported clock response or redirect')
        headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
        if any('hit' in headers.get(k, '').lower() for k in ('x-cache', 'cf-cache-status')):
            raise ClockSkewError('Cache-hit clock response forbidden')
        result = validate_sample(headers.get('date'), local_started, local_received,
            monotonic_started, monotonic_received, headers.get('age'))
    except ClockSkewError:
        raise
    except Exception:
        raise ClockSkewError('Remote clock check unavailable; no forecast') from None
    return dict(result, probe_url=URL, probe_nonce=nonce)


def require_fresh(sample, monotonic=time.monotonic, max_age=5.0):
    """Do not reuse a checked clock indefinitely or after a monotonic reset."""
    if not 0 < max_age <= 5 or sample.get('status') != 'wall_clock_consistent_not_absolute_utc_proof':
        raise ClockSkewError('Invalid clock sample')
    elapsed = monotonic()-sample['received_monotonic']
    if not math.isfinite(elapsed) or not 0 <= elapsed <= max_age:
        raise ClockSkewError('Stale clock sample; recheck before capture/dispatch')
    return sample
