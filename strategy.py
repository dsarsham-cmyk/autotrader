"""Strategy engine.

Strategies consume OHLCV candles and emit a Signal (BUY / SELL / HOLD).

Candle format: (timestamp, open, high, low, close, volume) — matching ccxt,
yfinance, and Alpaca bars.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from enum import Enum


class Signal(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


# ---------------------------------------------------------------------------
# Incremental indicator caches
# ---------------------------------------------------------------------------
# The backtester calls strategy.evaluate() with a growing candle window. Many
# indicators (closes, ema, atr) are O(n) to compute, so recomputing them on
# every bar makes the whole backtest O(n^2). These caches exploit the
# "same list object, +1 element" pattern: when the identical list grows by one
# bar, we extend the cached series in O(1) instead of recomputing in O(n).
#
# Each cache entry holds a strong reference to its input list so the list's
# id() cannot be recycled (and a stale entry can never be mistaken for a new
# list). Caches are bounded and cleared at the start of each simulation.

_EMA_CACHE: dict = {}
_ATR_CACHE: dict = {}
_CLOSES_CACHE: dict = {}
_CACHE_LIMIT = 512


def clear_indicators() -> None:
    """Drop all cached indicator series (called at the start of a simulation)."""
    _EMA_CACHE.clear()
    _ATR_CACHE.clear()
    _CLOSES_CACHE.clear()


def _bounded(cache: dict) -> None:
    if len(cache) > _CACHE_LIMIT:
        cache.clear()


def closes(candles: list) -> list[float]:
    """Extract close prices from candles (incrementally cached)."""
    key = id(candles)
    n = len(candles)
    hit = _CLOSES_CACHE.get(key)
    if hit is not None and hit[0] == n:
        return hit[1]
    if hit is not None and hit[0] == n - 1:
        # Extend in place so the returned list keeps the same identity — this
        # lets downstream ema()/atr() caches (keyed by id()) stay incremental.
        hit[1].append(candles[-1][4])
        _CLOSES_CACHE[key] = (n, hit[1], candles)
        _bounded(_CLOSES_CACHE)
        return hit[1]
    series = [c[4] for c in candles]
    _CLOSES_CACHE[key] = (n, series, candles)
    _bounded(_CLOSES_CACHE)
    return series


def highs(candles: list) -> list[float]:
    return [c[2] for c in candles]


def lows(candles: list) -> list[float]:
    return [c[3] for c in candles]


def atr(candles: list, period: int = 14) -> list[float]:
    """Average True Range (Wilder's smoothing) over the candle series.

    Incrementally cached: when the same candle list grows by one bar, only the
    newest ATR value is computed instead of the whole series.
    """
    key = (id(candles), period)
    n = len(candles)
    hit = _ATR_CACHE.get(key)
    if hit is not None and hit[0] == n:
        return hit[1]
    if hit is not None and hit[0] == n - 1 and n >= 2:
        out, trs = hit[1], hit[2]
        high, low, prev_close = candles[-1][2], candles[-1][3], candles[-2][4]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs = trs + [tr]
        out = out + [0.0]
        if n <= period:
            pass  # still in the all-zeros region
        elif n == period + 1:
            out[period] = sum(trs[1:period + 1]) / period
        else:
            out[n - 1] = (out[n - 2] * (period - 1) + trs[n - 1]) / period
        _ATR_CACHE[key] = (n, out, trs, candles)
        _bounded(_ATR_CACHE)
        return out
    if n < 2:
        out = [0.0] * n
        _ATR_CACHE[key] = (n, out, [0.0] * n, candles)
        return out
    trs = [0.0]
    for i in range(1, n):
        high, low, prev_close = candles[i][2], candles[i][3], candles[i - 1][4]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    # Wilder's smoothing
    out = [0.0] * n
    if n <= period:
        _ATR_CACHE[key] = (n, out, trs, candles)
        return out
    first = sum(trs[1:period + 1]) / period
    out[period] = first
    for i in range(period + 1, n):
        out[i] = (out[i - 1] * (period - 1) + trs[i]) / period
    _ATR_CACHE[key] = (n, out, trs, candles)
    _bounded(_ATR_CACHE)
    return out


def sma(values: list[float], period: int) -> float:
    return sum(values[-period:]) / period


def rolling_mean_std(values: list[float], period: int) -> tuple[float, float]:
    """Return (mean, std) of the last `period` values."""
    window = values[-period:]
    mean = sum(window) / period
    var = sum((x - mean) ** 2 for x in window) / period
    return mean, var ** 0.5


def ema(values: list[float], period: int) -> list[float]:
    """Exponential moving average (incrementally cached)."""
    key = (id(values), period)
    n = len(values)
    hit = _EMA_CACHE.get(key)
    if hit is not None and hit[0] == n:
        return hit[1]
    k = 2.0 / (period + 1)
    if hit is not None and hit[0] == n - 1 and n >= 2:
        series = hit[1] + [values[-1] * k + hit[1][-1] * (1 - k)]
        _EMA_CACHE[key] = (n, series, values)
        _bounded(_EMA_CACHE)
        return series
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    _EMA_CACHE[key] = (n, out, values)
    _bounded(_EMA_CACHE)
    return out


def day_of(ts_ms: float) -> str:
    """Return a date string for a millisecond timestamp (for day grouping)."""
    import datetime
    return datetime.datetime.fromtimestamp(ts_ms / 1000.0, datetime.UTC).strftime("%Y-%m-%d")


def todays_bars(candles: list) -> list:
    """Return the contiguous suffix of bars belonging to the most recent day.

    Walks backwards from the newest bar until the day changes, so it is
    O(bars per day) instead of scanning the whole series (which made the
    VWAP / gap strategies O(n^2) inside the backtester).
    """
    if not candles:
        return []
    today = day_of(candles[-1][0])
    out = []
    for c in reversed(candles):
        if day_of(c[0]) != today:
            break
        out.append(c)
    out.reverse()
    return out


def realized_vol(candles: list, period: int = 20) -> float:
    """Realized volatility (std of close-to-close returns) over the last `period` bars."""
    c = closes(candles)
    if len(c) < period + 1:
        return 0.0
    rets = [c[i] / c[i - 1] - 1.0 for i in range(len(c) - period, len(c))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return var ** 0.5


class Strategy(ABC):
    """Base class for all strategies."""

    warmup: int = 60  # minimum candles needed before evaluate() is meaningful

    @abstractmethod
    def evaluate(self, candles: list) -> Signal:
        """Return a Signal given candles (oldest -> newest)."""

    def describe(self, candles: list) -> dict:
        """Return key indicator values for diagnostics/display."""
        return {}


class MovingAverageCrossover(Strategy):
    """Fast/slow moving-average crossover (golden/death cross)."""

    def __init__(self, fast_period: int = 20, slow_period: int = 50):
        if fast_period >= slow_period:
            raise ValueError("fast_period must be smaller than slow_period")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.warmup = slow_period + 1

    def evaluate(self, candles: list) -> Signal:
        c = closes(candles)
        if len(c) < self.slow_period + 1:
            return Signal.HOLD
        fast_now, slow_now = sma(c, self.fast_period), sma(c, self.slow_period)
        fast_prev, slow_prev = sma(c[:-1], self.fast_period), sma(c[:-1], self.slow_period)
        if fast_prev <= slow_prev and fast_now > slow_now:
            return Signal.BUY
        if fast_prev >= slow_prev and fast_now < slow_now:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        c = closes(candles)
        if len(c) < self.slow_period + 1:
            return {}
        return {"fast_sma": round(sma(c, self.fast_period), 4),
                "slow_sma": round(sma(c, self.slow_period), 4)}


class RSI(Strategy):
    """Relative Strength Index with overbought/oversold thresholds."""

    def __init__(self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.warmup = period + 1

    def _rsi(self, c: list[float]) -> float:
        if len(c) < self.period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(c)):
            change = c[i] - c[i - 1]
            gains.append(max(change, 0.0))
            losses.append(max(-change, 0.0))
        avg_gain = sum(gains[-self.period:]) / self.period
        avg_loss = sum(losses[-self.period:]) / self.period
        if avg_loss == 0:
            return 100.0
        return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

    def evaluate(self, candles: list) -> Signal:
        c = closes(candles)
        if len(c) < self.period + 1:
            return Signal.HOLD
        rsi_now, rsi_prev = self._rsi(c), self._rsi(c[:-1])
        if rsi_prev <= self.oversold and rsi_now > self.oversold:
            return Signal.BUY
        if rsi_prev >= self.overbought and rsi_now < self.overbought:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        return {"rsi": round(self._rsi(closes(candles)), 2)}


class BollingerBands(Strategy):
    """Mean-reversion at the Bollinger Bands."""

    def __init__(self, period: int = 20, num_std: float = 2.0):
        self.period = period
        self.num_std = num_std
        self.warmup = period + 1

    def _bands(self, c: list[float]) -> tuple[float, float, float]:
        window = c[-self.period:]
        mean = sum(window) / self.period
        var = sum((x - mean) ** 2 for x in window) / self.period
        std = var ** 0.5
        return mean - self.num_std * std, mean, mean + self.num_std * std

    def evaluate(self, candles: list) -> Signal:
        c = closes(candles)
        if len(c) < self.period + 1:
            return Signal.HOLD
        lo_n, _, up_n = self._bands(c)
        lo_p, _, up_p = self._bands(c[:-1])
        if c[-2] <= lo_p and c[-1] > lo_n:
            return Signal.BUY
        if c[-2] >= up_p and c[-1] < up_n:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        c = closes(candles)
        if len(c) < self.period + 1:
            return {}
        lo, mid, up = self._bands(c)
        return {"lower": round(lo, 4), "middle": round(mid, 4), "upper": round(up, 4)}


class MACD(Strategy):
    """MACD line vs signal line crossover."""

    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.warmup = slow_period + signal_period + 1

    def evaluate(self, candles: list) -> Signal:
        c = closes(candles)
        if len(c) < self.slow_period + self.signal_period + 1:
            return Signal.HOLD
        macd = [f - s for f, s in zip(ema(c, self.fast_period), ema(c, self.slow_period))]
        signal = ema(macd, self.signal_period)
        if macd[-1] > signal[-1] and macd[-2] <= signal[-2]:
            return Signal.BUY
        if macd[-1] < signal[-1] and macd[-2] >= signal[-2]:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        c = closes(candles)
        if len(c) < self.slow_period + self.signal_period + 1:
            return {}
        macd = [f - s for f, s in zip(ema(c, self.fast_period), ema(c, self.slow_period))]
        sig = ema(macd, self.signal_period)
        return {"macd": round(macd[-1], 4), "signal": round(sig[-1], 4)}


class TrendFollowing(Strategy):
    """Volatility-aware trend following.

    - Regime filter: only long when price is above the long-term SMA.
    - Entry: fast EMA crosses above slow EMA (momentum confirmation).
    - Exit: fast EMA crosses back below slow EMA.

    Position sizing and stops (ATR-based) are handled by the risk layer, not
    here — this strategy only decides direction/timing.
    """

    def __init__(self, fast_period: int = 20, slow_period: int = 50,
                 trend_period: int = 200):
        if fast_period >= slow_period:
            raise ValueError("fast_period must be smaller than slow_period")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.trend_period = trend_period
        self.warmup = trend_period + 1

    def evaluate(self, candles: list) -> Signal:
        c = closes(candles)
        if len(c) < self.trend_period + 1:
            return Signal.HOLD

        # Regime: only trade in the direction of the long-term trend.
        uptrend = c[-1] > sma(c, self.trend_period)

        fast = ema(c, self.fast_period)
        slow = ema(c, self.slow_period)
        cross_up = fast[-1] > slow[-1] and fast[-2] <= slow[-2]
        cross_down = fast[-1] < slow[-1] and fast[-2] >= slow[-2]

        if uptrend and cross_up:
            return Signal.BUY
        if cross_down:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        c = closes(candles)
        if len(c) < self.trend_period + 1:
            return {}
        return {"fast_ema": round(ema(c, self.fast_period)[-1], 4),
                "slow_ema": round(ema(c, self.slow_period)[-1], 4),
                "trend_sma": round(sma(c, self.trend_period), 4),
                "uptrend": bool(c[-1] > sma(c, self.trend_period))}


class DonchianBreakout(Strategy):
    """Turtle-style breakout (Richard Dennis / Curtis Faith).

    BUY  when close breaks above the prior N-day high.
    SELL when close breaks below the prior M-day low.
    """

    def __init__(self, entry_period: int = 20, exit_period: int = 10):
        self.entry_period = entry_period
        self.exit_period = exit_period
        self.warmup = entry_period + 1

    def evaluate(self, candles: list) -> Signal:
        c = closes(candles)
        if len(c) < self.entry_period + 1:
            return Signal.HOLD
        # Prior N-day high (excluding current bar).
        entry_high = max(highs(candles)[-self.entry_period - 1:-1])
        exit_low = min(lows(candles)[-self.exit_period - 1:-1])
        if c[-1] > entry_high:
            return Signal.BUY
        if c[-1] < exit_low:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        if len(candles) < self.entry_period + 1:
            return {}
        entry_high = max(highs(candles)[-self.entry_period - 1:-1])
        exit_low = min(lows(candles)[-self.exit_period - 1:-1])
        return {"entry_high": round(entry_high, 4), "exit_low": round(exit_low, 4)}


class VolatilityBreakout(Strategy):
    """Keltner-channel breakout with RSI + trend confirmation.

    BUY when close breaks above the upper Keltner band (EMA + k*ATR), RSI is
    strong (> threshold), and price is above the EMA (uptrend).
    SELL when close falls back below the EMA.
    """

    def __init__(self, ema_period: int = 20, atr_period: int = 14,
                 atr_mult: float = 2.0, rsi_period: int = 14,
                 rsi_threshold: float = 60.0):
        self.ema_period = ema_period
        self.atr_period = atr_period
        self.atr_mult = atr_mult
        self.rsi_period = rsi_period
        self.rsi_threshold = rsi_threshold
        self.warmup = max(ema_period, atr_period, rsi_period) + 1

    def _rsi(self, c: list[float]) -> float:
        if len(c) < self.rsi_period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(c)):
            ch = c[i] - c[i - 1]
            gains.append(max(ch, 0.0))
            losses.append(max(-ch, 0.0))
        ag = sum(gains[-self.rsi_period:]) / self.rsi_period
        al = sum(losses[-self.rsi_period:]) / self.rsi_period
        if al == 0:
            return 100.0
        return 100.0 - (100.0 / (1.0 + ag / al))

    def evaluate(self, candles: list) -> Signal:
        c = closes(candles)
        if len(c) < self.warmup:
            return Signal.HOLD
        ema_line = ema(c, self.ema_period)[-1]
        a = atr(candles, self.atr_period)[-1]
        upper = ema_line + self.atr_mult * a
        rsi_val = self._rsi(c)
        if c[-1] > upper and rsi_val > self.rsi_threshold and c[-1] > ema_line:
            return Signal.BUY
        if c[-1] < ema_line:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        c = closes(candles)
        if len(c) < self.warmup:
            return {}
        ema_line = ema(c, self.ema_period)[-1]
        a = atr(candles, self.atr_period)[-1]
        return {"ema": round(ema_line, 4),
                "upper_band": round(ema_line + self.atr_mult * a, 4),
                "rsi": round(self._rsi(c), 2)}


class ZScoreMeanReversion(Strategy):
    """Z-score mean reversion.

    BUY  when price is `entry` standard deviations below its rolling mean.
    SELL when price reverts back to within `exit` standard deviations.
    """

    def __init__(self, period: int = 50, entry_z: float = 2.0, exit_z: float = 0.5):
        self.period = period
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.warmup = period + 1

    def evaluate(self, candles: list) -> Signal:
        c = closes(candles)
        if len(c) < self.period + 1:
            return Signal.HOLD
        mean, std = rolling_mean_std(c, self.period)
        if std == 0:
            return Signal.HOLD
        z = (c[-1] - mean) / std
        if z <= -self.entry_z:
            return Signal.BUY
        if z >= -self.exit_z and z < 0:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        c = closes(candles)
        if len(c) < self.period + 1:
            return {}
        mean, std = rolling_mean_std(c, self.period)
        z = (c[-1] - mean) / std if std else 0.0
        return {"z_score": round(z, 2), "mean": round(mean, 4), "std": round(std, 4)}


class TimeSeriesMomentum(Strategy):
    """12-month time-series momentum (Moskowitz, Ooi, Pedersen 2012).

    The most academically-validated strategy. Holds long while the trailing
    N-day return is positive, exits when it turns negative. Trend persists for
    1-12 months, so the 252-day (12-month) lookback is the dominant horizon.
    """

    def __init__(self, lookback: int = 252):
        self.lookback = lookback
        self.warmup = lookback + 1

    def evaluate(self, candles: list) -> Signal:
        c = closes(candles)
        if len(c) < self.lookback + 1:
            return Signal.HOLD
        ret = c[-1] / c[-self.lookback] - 1.0
        if ret > 0:
            return Signal.BUY
        return Signal.SELL

    def describe(self, candles: list) -> dict:
        c = closes(candles)
        if len(c) < self.lookback + 1:
            return {}
        return {"lookback_return_pct": round((c[-1] / c[-self.lookback] - 1.0) * 100, 2)}


class OpeningRangeBreakout(Strategy):
    """Opening Range Breakout (ORB) — the classic day-trading strategy.

    The opening range is the first `or_bars` bars of the trading day. Buy when
    price breaks above the opening-range high, sell when it breaks below the
    low. Positions are closed at end of day (handled by the execution layer).
    """

    def __init__(self, or_bars: int = 2):
        self.or_bars = or_bars
        self.warmup = or_bars + 1

    def evaluate(self, candles: list) -> Signal:
        if len(candles) < self.or_bars + 1:
            return Signal.HOLD
        today = day_of(candles[-1][0])
        # Collect today's bars (walk back until the day changes).
        todays = []
        for c in reversed(candles):
            if day_of(c[0]) != today:
                break
            todays.append(c)
        todays.reverse()
        if len(todays) < self.or_bars + 1:
            return Signal.HOLD
        or_high = max(c[2] for c in todays[:self.or_bars])
        or_low = min(c[3] for c in todays[:self.or_bars])
        close = candles[-1][4]
        if close > or_high:
            return Signal.BUY
        if close < or_low:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        if len(candles) < self.or_bars + 1:
            return {}
        today = day_of(candles[-1][0])
        todays = []
        for c in reversed(candles):
            if day_of(c[0]) != today:
                break
            todays.append(c)
        todays.reverse()
        if len(todays) < self.or_bars + 1:
            return {}
        return {"or_high": round(max(c[2] for c in todays[:self.or_bars]), 4),
                "or_low": round(min(c[3] for c in todays[:self.or_bars]), 4)}


class IntradayMomentum(Strategy):
    """Intraday momentum: fast/slow EMA crossover on intraday bars.

    Same logic as the MA crossover, but intended for intraday timeframes with
    end-of-day position closure (handled by the execution layer).
    """

    def __init__(self, fast_period: int = 5, slow_period: int = 15):
        if fast_period >= slow_period:
            raise ValueError("fast_period must be smaller than slow_period")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.warmup = slow_period + 1

    def evaluate(self, candles: list) -> Signal:
        c = closes(candles)
        if len(c) < self.slow_period + 1:
            return Signal.HOLD
        fast = ema(c, self.fast_period)
        slow = ema(c, self.slow_period)
        if fast[-1] > slow[-1] and fast[-2] <= slow[-2]:
            return Signal.BUY
        if fast[-1] < slow[-1] and fast[-2] >= slow[-2]:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        c = closes(candles)
        if len(c) < self.slow_period + 1:
            return {}
        f = ema(c, self.fast_period)[-1]
        s = ema(c, self.slow_period)[-1]
        return {"fast_ema": round(f, 4), "slow_ema": round(s, 4),
                "spread": round(f - s, 4)}


class VolatilityScaledMomentum(Strategy):
    """Time-series momentum with a volatility filter (Barroso & Santa-Clara 2015).

    Long when the trailing N-bar return is positive AND realized volatility is
    within a normal band (i.e. not a crash regime). Exits when the return turns
    negative. The volatility filter avoids entering during momentum crashes
    (Daniel & Moskowitz 2016), the single biggest risk of raw momentum.
    """

    def __init__(self, lookback: int = 252, vol_period: int = 20,
                 vol_baseline: int = 252, vol_mult: float = 2.0):
        self.lookback = lookback
        self.vol_period = vol_period
        self.vol_baseline = vol_baseline
        self.vol_mult = vol_mult
        self.warmup = max(lookback, vol_baseline) + 1

    def evaluate(self, candles: list) -> Signal:
        c = closes(candles)
        if len(c) < self.warmup:
            return Signal.HOLD
        ret = c[-1] / c[-self.lookback] - 1.0
        vol_now = realized_vol(candles, self.vol_period)
        vol_base = realized_vol(candles, self.vol_baseline)
        if vol_base <= 0:
            return Signal.HOLD
        vol_ratio = vol_now / vol_base
        if ret > 0 and vol_ratio <= self.vol_mult:
            return Signal.BUY
        if ret <= 0:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        c = closes(candles)
        if len(c) < self.warmup:
            return {}
        ret = c[-1] / c[-self.lookback] - 1.0
        vol_now = realized_vol(candles, self.vol_period)
        vol_base = realized_vol(candles, self.vol_baseline)
        return {"lookback_return_pct": round(ret * 100, 2),
                "vol_ratio": round(vol_now / vol_base, 3) if vol_base else 0.0}


class RegimeAdaptive(Strategy):
    """Regime-switching: momentum in trends, mean-reversion in ranges.

    Detects the regime via trend strength (distance between fast and slow EMA,
    normalized by ATR). In a strong trend it trades momentum (EMA crossover
    direction); in a range it trades mean-reversion (z-score of price vs its
    rolling mean). This is the recurring "modern edge" in 2024-2026 literature:
    momentum and mean-reversion are regime-dependent, not always-on.
    """

    def __init__(self, fast_period: int = 20, slow_period: int = 50,
                 trend_threshold: float = 1.0, mean_period: int = 50,
                 entry_z: float = 2.0, exit_z: float = 0.5):
        if fast_period >= slow_period:
            raise ValueError("fast_period must be smaller than slow_period")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.trend_threshold = trend_threshold
        self.mean_period = mean_period
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.warmup = max(slow_period, mean_period) + 1

    def _trend_strength(self, candles: list) -> float:
        """|fast EMA - slow EMA| / ATR — a normalized trend-strength measure."""
        c = closes(candles)
        fast = ema(c, self.fast_period)[-1]
        slow = ema(c, self.slow_period)[-1]
        a = atr(candles, period=14)[-1]
        if a <= 0:
            return 0.0
        return abs(fast - slow) / a

    def evaluate(self, candles: list) -> Signal:
        c = closes(candles)
        if len(c) < self.warmup:
            return Signal.HOLD

        trending = self._trend_strength(candles) >= self.trend_threshold

        if trending:
            # Momentum: follow the EMA relationship (state, not edge).
            fast = ema(c, self.fast_period)[-1]
            slow = ema(c, self.slow_period)[-1]
            if fast > slow:
                return Signal.BUY
            return Signal.SELL

        # Range: mean-reversion on the z-score of price vs its rolling mean.
        mean, std = rolling_mean_std(c, self.mean_period)
        if std <= 0:
            return Signal.HOLD
        z = (c[-1] - mean) / std
        if z <= -self.entry_z:
            return Signal.BUY
        if z >= -self.exit_z and z < 0:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        c = closes(candles)
        if len(c) < self.warmup:
            return {}
        mean, std = rolling_mean_std(c, self.mean_period)
        z = (c[-1] - mean) / std if std else 0.0
        return {"trend_strength": round(self._trend_strength(candles), 3),
                "regime": "trend" if self._trend_strength(candles) >= self.trend_threshold else "range",
                "z_score": round(z, 2)}


class PairsTrading:
    """Pairs trading / statistical arbitrage: mean-reversion on the log price
    ratio of two correlated assets (e.g. QQQ vs SPY, EWJ vs EZU).

    spread = log(close_a) - log(close_b)
    z      = z-score of the spread over a rolling window.

    When one leg becomes expensive relative to the other (|z| > entry_z), short
    the expensive leg and long the cheap leg, betting on convergence. Exit when
    the spread reverts toward its mean (|z| < exit_z).

    This is a long-short strategy (requires a broker that supports shorting,
    e.g. Alpaca). It is not a single-symbol `Strategy`, so it is not registered
    in `STRATEGIES` — it is driven by the dedicated pairs runner in `pairs.py`.
    """

    def __init__(self, window: int = 50, entry_z: float = 2.0, exit_z: float = 0.5):
        self.window = window
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.warmup = window + 1

    def zscore(self, candles_a: list, candles_b: list) -> float | None:
        """Return the current z-score of the log price ratio, or None if there
        is insufficient data."""
        ca = closes(candles_a)
        cb = closes(candles_b)
        n = min(len(ca), len(cb))
        if n < self.warmup:
            return None
        spread = [math.log(ca[i]) - math.log(cb[i]) for i in range(n)]
        mean, std = rolling_mean_std(spread, self.window)
        if std <= 0:
            return 0.0
        return (spread[-1] - mean) / std

    def signal(self, candles_a: list, candles_b: list) -> tuple[str, float]:
        """Return (action, z) where action is one of:

        - 'long_a'  -> long A + short B (A is cheap relative to B)
        - 'short_a' -> short A + long B (A is expensive relative to B)
        - 'flat'    -> no position (spread not extreme, or converged)
        - 'hold'    -> keep the current position (between entry and exit)
        """
        z = self.zscore(candles_a, candles_b)
        if z is None:
            return "flat", 0.0
        if z > self.entry_z:
            return "short_a", z
        if z < -self.entry_z:
            return "long_a", z
        if abs(z) < self.exit_z:
            return "flat", z
        return "hold", z

    def describe(self, candles_a: list, candles_b: list) -> dict:
        z = self.zscore(candles_a, candles_b)
        return {"z_score": round(z, 2) if z is not None else None}


class VWAPMeanReversion(Strategy):
    """Intraday mean reversion around VWAP (volume-weighted average price).

    BUY when price dips below VWAP (oversold), SELL when it reverts back to
    VWAP. A classic institutional day-trading mean-reversion signal. Uses the
    typical price (H+L+C)/3 weighted by volume over the current trading day.
    """

    def __init__(self, band_pct: float = 0.3):
        self.band_pct = band_pct   # % below VWAP to enter
        self.warmup = 20

    def _vwap(self, candles: list) -> float | None:
        todays = todays_bars(candles)
        if not todays:
            return None
        pv = sum((c[2] + c[3] + c[4]) / 3.0 * c[5] for c in todays)
        v = sum(c[5] for c in todays)
        if v <= 0:
            return None
        return pv / v

    def evaluate(self, candles: list) -> Signal:
        if len(candles) < self.warmup:
            return Signal.HOLD
        vwap = self._vwap(candles)
        if vwap is None:
            return Signal.HOLD
        price = candles[-1][4]
        if price < vwap * (1 - self.band_pct / 100.0):
            return Signal.BUY
        if price >= vwap:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        vwap = self._vwap(candles)
        if vwap is None:
            return {}
        return {"vwap": round(vwap, 4),
                "price": round(candles[-1][4], 4),
                "dist_pct": round((candles[-1][4] / vwap - 1) * 100, 2)}


class GapAndGo(Strategy):
    """Gap-and-go momentum: trade the opening gap direction.

    BUY when the market gaps up (today's open > yesterday's close) and price
    holds above the open (momentum continuation). SELL when it gaps down and
    price holds below the open. A popular retail day-trading setup.
    """

    def __init__(self, gap_pct: float = 0.3):
        self.gap_pct = gap_pct   # minimum gap size in %
        self.warmup = 2

    def evaluate(self, candles: list) -> Signal:
        if len(candles) < 2:
            return Signal.HOLD
        todays = todays_bars(candles)
        if len(todays) < 2 or len(todays) >= len(candles):
            return Signal.HOLD
        prev_close = candles[-len(todays) - 1][4]
        open_price = todays[0][1]
        gap = (open_price / prev_close - 1.0) * 100
        price = candles[-1][4]
        if gap > self.gap_pct and price > open_price:
            return Signal.BUY
        if gap < -self.gap_pct and price < open_price:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        today = day_of(candles[-1][0])
        todays = [c for c in candles if day_of(c[0]) == today]
        prev = [c for c in candles if day_of(c[0]) != today]
        if not todays or not prev:
            return {}
        gap = (todays[0][1] / prev[-1][4] - 1.0) * 100
        return {"gap_pct": round(gap, 2),
                "open": round(todays[0][1], 4),
                "prev_close": round(prev[-1][4], 4)}


class VolumeBreakout(Strategy):
    """Breakout above the prior N-bar high with volume confirmation.

    BUY when price breaks above the prior high AND volume spikes above its
    average (confirms the breakout is real, not a fakeout). SELL when price
    falls back below the prior low. Volume is a leading confirmation signal
    for momentum breakouts.
    """

    def __init__(self, lookback: int = 20, vol_mult: float = 2.0):
        self.lookback = lookback
        self.vol_mult = vol_mult
        self.warmup = lookback + 1

    def evaluate(self, candles: list) -> Signal:
        if len(candles) < self.lookback + 1:
            return Signal.HOLD
        prior_high = max(c[2] for c in candles[-self.lookback - 1:-1])
        prior_low = min(c[3] for c in candles[-self.lookback - 1:-1])
        price = candles[-1][4]
        vol = candles[-1][5]
        avg_vol = sum(c[5] for c in candles[-self.lookback - 1:-1]) / self.lookback
        if price > prior_high and avg_vol > 0 and vol > self.vol_mult * avg_vol:
            return Signal.BUY
        if price < prior_low:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        if len(candles) < self.lookback + 1:
            return {}
        prior_high = max(c[2] for c in candles[-self.lookback - 1:-1])
        avg_vol = sum(c[5] for c in candles[-self.lookback - 1:-1]) / self.lookback
        return {"prior_high": round(prior_high, 4),
                "price": round(candles[-1][4], 4),
                "vol_ratio": round(candles[-1][5] / avg_vol, 2) if avg_vol else 0.0}


class CompositeStrategy(Strategy):
    """Combine multiple strategies into a single signal.

    BUY  if any sub-strategy says BUY (and none says SELL).
    SELL if any sub-strategy says SELL (and none says BUY).
    HOLD on conflict (e.g. a breakout to new highs while already overbought).

    Lets one bot trade both breakouts (up days) and mean-reversion dips
    (down days) from a single strategy slot.
    """

    def __init__(self, strategies: list[Strategy]):
        self.strategies = strategies
        self.warmup = max(s.warmup for s in strategies) if strategies else 60

    def evaluate(self, candles: list) -> Signal:
        signals = [s.evaluate(candles) for s in self.strategies]
        has_buy = Signal.BUY in signals
        has_sell = Signal.SELL in signals
        if has_buy and not has_sell:
            return Signal.BUY
        if has_sell and not has_buy:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        out = {}
        for s in self.strategies:
            d = s.describe(candles)
            prefix = type(s).__name__
            for k, v in d.items():
                out[f"{prefix}.{k}"] = v
        return out


class Supertrend(Strategy):
    """ATR-based Supertrend (a popular day-trading trend filter).

    BUY  when price crosses above the supertrend line (downtrend -> uptrend).
    SELL when price crosses below it (uptrend -> downtrend). The line is a
    trailing ATR band that flips sides with the trend.
    """

    def __init__(self, period: int = 10, multiplier: float = 3.0):
        self.period = period
        self.multiplier = multiplier
        self.warmup = period + 2
        self._st_cache_key = None
        self._st_cache = None  # (st, direction, fu, fl)

    def _supertrend(self, candles: list) -> tuple[list[float], list[int]]:
        n = len(candles)
        key = (id(candles), n)
        if self._st_cache_key == key:
            return self._st_cache[0], self._st_cache[1]

        a = atr(candles, self.period)

        # Incremental extension: the same candle list grew by one bar, so only
        # the newest supertrend value needs computing (avoids O(n^2) backtests).
        if (self._st_cache is not None and self._st_cache_key is not None
                and self._st_cache_key[0] == id(candles)
                and self._st_cache_key[1] == n - 1 and n >= 2):
            st, direction, fu, fl = self._st_cache
            i = n - 1
            hl2 = (candles[i][2] + candles[i][3]) / 2.0
            bu = hl2 + self.multiplier * a[i]
            bl = hl2 - self.multiplier * a[i]
            fu.append(bu if (bu < fu[i - 1] or candles[i - 1][4] > fu[i - 1]) else fu[i - 1])
            fl.append(bl if (bl > fl[i - 1] or candles[i - 1][4] < fl[i - 1]) else fl[i - 1])
            if st[i - 1] == fu[i - 1]:
                if candles[i][4] <= fu[i]:
                    st.append(fu[i]); direction.append(-1)
                else:
                    st.append(fl[i]); direction.append(1)
            else:
                if candles[i][4] >= fl[i]:
                    st.append(fl[i]); direction.append(1)
                else:
                    st.append(fu[i]); direction.append(-1)
            self._st_cache_key = key
            self._st_cache = (st, direction, fu, fl)
            return st, direction

        # Full recompute.
        st = [0.0] * n
        direction = [0] * n
        fu = [0.0] * n
        fl = [0.0] * n
        for i in range(n):
            hl2 = (candles[i][2] + candles[i][3]) / 2.0
            bu = hl2 + self.multiplier * a[i]
            bl = hl2 - self.multiplier * a[i]
            if i == 0:
                fu[i], fl[i] = bu, bl
                st[i], direction[i] = bu, 1
                continue
            fu[i] = bu if (bu < fu[i - 1] or candles[i - 1][4] > fu[i - 1]) else fu[i - 1]
            fl[i] = bl if (bl > fl[i - 1] or candles[i - 1][4] < fl[i - 1]) else fl[i - 1]
            if st[i - 1] == fu[i - 1]:
                if candles[i][4] <= fu[i]:
                    st[i], direction[i] = fu[i], -1
                else:
                    st[i], direction[i] = fl[i], 1
            else:
                if candles[i][4] >= fl[i]:
                    st[i], direction[i] = fl[i], 1
                else:
                    st[i], direction[i] = fu[i], -1
        self._st_cache_key = key
        self._st_cache = (st, direction, fu, fl)
        return st, direction

    def evaluate(self, candles: list) -> Signal:
        if len(candles) < self.warmup:
            return Signal.HOLD
        _, direction = self._supertrend(candles)
        if direction[-2] == -1 and direction[-1] == 1:
            return Signal.BUY
        if direction[-2] == 1 and direction[-1] == -1:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        st, direction = self._supertrend(candles)
        return {"supertrend": round(st[-1], 4),
                "trend": "up" if direction[-1] == 1 else "down"}


class Stochastic(Strategy):
    """Stochastic oscillator (%K/%D) momentum cross.

    BUY  when %K crosses above %D while oversold.
    SELL when %K crosses below %D while overbought. Complements RSI with a
    faster, range-based oscillator.
    """

    def __init__(self, k_period: int = 14, d_period: int = 3,
                 oversold: float = 20.0, overbought: float = 80.0):
        self.k_period = k_period
        self.d_period = d_period
        self.oversold = oversold
        self.overbought = overbought
        self.warmup = k_period + d_period + 1

    def _stoch(self, candles: list) -> tuple[list[float], list[float]]:
        n = len(candles)
        k_vals = [50.0] * n
        for i in range(self.k_period - 1, n):
            window = candles[i - self.k_period + 1:i + 1]
            hh = max(c[2] for c in window)
            ll = min(c[3] for c in window)
            k_vals[i] = 50.0 if hh == ll else (candles[i][4] - ll) / (hh - ll) * 100.0
        d_vals = [50.0] * n
        for i in range(self.k_period + self.d_period - 2, n):
            d_vals[i] = sum(k_vals[i - self.d_period + 1:i + 1]) / self.d_period
        return k_vals, d_vals

    def evaluate(self, candles: list) -> Signal:
        if len(candles) < self.warmup:
            return Signal.HOLD
        k, d = self._stoch(candles)
        k_now, k_prev = k[-1], k[-2]
        d_now, d_prev = d[-1], d[-2]
        if k_prev <= d_prev and k_now > d_now and k_now < self.oversold:
            return Signal.BUY
        if k_prev >= d_prev and k_now < d_now and k_now > self.overbought:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        k, d = self._stoch(candles)
        return {"stoch_k": round(k[-1], 2), "stoch_d": round(d[-1], 2)}


class KeltnerChannelBreakout(Strategy):
    """Keltner channel breakout (volatility breakout).

    BUY  when price breaks above EMA + mult*ATR.
    SELL when price breaks below EMA - mult*ATR. Unlike Bollinger (std-dev),
    Keltner uses ATR, so it tracks volatility breakouts rather than reversion.
    """

    def __init__(self, period: int = 20, atr_period: int = 10, mult: float = 2.0):
        self.period = period
        self.atr_period = atr_period
        self.mult = mult
        self.warmup = max(period, atr_period) + 2

    def evaluate(self, candles: list) -> Signal:
        if len(candles) < self.warmup:
            return Signal.HOLD
        c = closes(candles)
        mid = ema(c, self.period)
        a = atr(candles, self.atr_period)
        price = candles[-1][4]
        prev_price = candles[-2][4]
        upper = mid[-1] + self.mult * a[-1]
        lower = mid[-1] - self.mult * a[-1]
        prev_upper = mid[-2] + self.mult * a[-2]
        prev_lower = mid[-2] - self.mult * a[-2]
        if prev_price <= prev_upper and price > upper:
            return Signal.BUY
        if prev_price >= prev_lower and price < lower:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        c = closes(candles)
        mid = ema(c, self.period)
        a = atr(candles, self.atr_period)
        return {"mid": round(mid[-1], 4),
                "upper": round(mid[-1] + self.mult * a[-1], 4),
                "lower": round(mid[-1] - self.mult * a[-1], 4)}


class NR7Breakout(Strategy):
    """Narrow-range (NR7) breakout — volatility contraction then expansion.

    When the prior bar has the narrowest range of the last N bars (a coiled
    spring), BUY a break above its high / SELL a break below its low. A classic
    day-trading setup for catching the start of a new impulse move.
    """

    def __init__(self, n: int = 7):
        self.n = n
        self.warmup = n + 2

    def evaluate(self, candles: list) -> Signal:
        if len(candles) < self.warmup:
            return Signal.HOLD
        prev = candles[-2]
        prev_range = prev[2] - prev[3]
        # Compare the prior bar's range against the n-1 bars before it.
        window = candles[-self.n - 1:-2]
        ranges = [c[2] - c[3] for c in window]
        if not ranges or prev_range >= min(ranges):
            return Signal.HOLD
        price = candles[-1][4]
        if price > prev[2]:
            return Signal.BUY
        if price < prev[3]:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        prev = candles[-2]
        window = candles[-self.n - 1:-2]
        ranges = [c[2] - c[3] for c in window]
        nr7 = bool(ranges) and (prev[2] - prev[3]) < min(ranges)
        return {"nr7": nr7, "range": round(prev[2] - prev[3], 4),
                "breakout_high": round(prev[2], 4), "breakout_low": round(prev[3], 4)}


class DirectionalMomentum(Strategy):
    """Directional momentum model — predicts up/down on every bar.

    Combines EMA trend and rate-of-change into a single direction score and
    stays LONG while the score is positive, FLAT while negative. Unlike the
    trigger strategies (breakout/oversold/NR7) that mostly sit in HOLD, this
    always has a directional view, so the bot is positioned most of the time.

        score = (fast_ema - slow_ema) / slow_ema + rate_of_change
    """

    def __init__(self, fast_period: int = 8, slow_period: int = 21,
                 roc_period: int = 12, deadband: float = 0.0):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.roc_period = roc_period
        self.deadband = deadband
        self.warmup = max(slow_period, roc_period) + 2

    def _score(self, candles: list) -> float:
        c = closes(candles)
        fast = ema(c, self.fast_period)[-1]
        slow = ema(c, self.slow_period)[-1]
        roc = c[-1] / c[-self.roc_period - 1] - 1.0
        return (fast - slow) / slow + roc

    def evaluate(self, candles: list) -> Signal:
        if len(candles) < self.warmup:
            return Signal.HOLD
        score = self._score(candles)
        if score > self.deadband:
            return Signal.BUY
        if score < -self.deadband:
            return Signal.SELL
        return Signal.HOLD

    def describe(self, candles: list) -> dict:
        c = closes(candles)
        fast = ema(c, self.fast_period)[-1]
        slow = ema(c, self.slow_period)[-1]
        roc = c[-1] / c[-self.roc_period - 1] - 1.0
        return {"fast_ema": round(fast, 4), "slow_ema": round(slow, 4),
                "roc_pct": round(roc * 100, 2),
                "score": round(self._score(candles) * 100, 3)}


class VWAPTrend(Strategy):
    """VWAP trend filter (Zarattini & Aziz 2023).

    LONG when price is above the day's VWAP (uptrend — VWAP acts as dynamic
    support), FLAT/SHORT when below. The opposite of VWAPMeanReversion: here
    VWAP is a trend line, not a reversion target. Validated on QQQ/TQQQ.
    """

    def __init__(self, warmup: int = 20):
        self.warmup = warmup

    def _vwap(self, candles: list) -> float | None:
        todays = todays_bars(candles)
        if not todays:
            return None
        pv = sum((c[2] + c[3] + c[4]) / 3.0 * c[5] for c in todays)
        v = sum(c[5] for c in todays)
        if v <= 0:
            return None
        return pv / v

    def evaluate(self, candles: list) -> Signal:
        if len(candles) < self.warmup:
            return Signal.HOLD
        vwap = self._vwap(candles)
        if vwap is None:
            return Signal.HOLD
        if candles[-1][4] > vwap:
            return Signal.BUY
        return Signal.SELL

    def describe(self, candles: list) -> dict:
        vwap = self._vwap(candles)
        if vwap is None:
            return {}
        return {"vwap": round(vwap, 4),
                "price": round(candles[-1][4], 4),
                "dist_pct": round((candles[-1][4] / vwap - 1) * 100, 2)}


STRATEGIES = {
    "moving_average_crossover": MovingAverageCrossover,
    "rsi": RSI,
    "bollinger_bands": BollingerBands,
    "macd": MACD,
    "trend_following": TrendFollowing,
    "donchian_breakout": DonchianBreakout,
    "volatility_breakout": VolatilityBreakout,
    "zscore_mean_reversion": ZScoreMeanReversion,
    "time_series_momentum": TimeSeriesMomentum,
    "opening_range_breakout": OpeningRangeBreakout,
    "intraday_momentum": IntradayMomentum,
    "volatility_scaled_momentum": VolatilityScaledMomentum,
    "regime_adaptive": RegimeAdaptive,
    "vwap_mean_reversion": VWAPMeanReversion,
    "gap_and_go": GapAndGo,
    "volume_breakout": VolumeBreakout,
    "supertrend": Supertrend,
    "stochastic": Stochastic,
    "keltner_breakout": KeltnerChannelBreakout,
    "nr7_breakout": NR7Breakout,
    "directional_momentum": DirectionalMomentum,
    "vwap_trend": VWAPTrend,
}


def build_strategy(config: dict) -> Strategy:
    name = config.get("name", "trend_following")
    if name == "composite":
        subs = [build_strategy(sc) for sc in config.get("strategies", [])]
        return CompositeStrategy(subs)
    params = {k: v for k, v in config.items() if k != "name"}
    cls = STRATEGIES.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name!r}")
    return cls(**params)
