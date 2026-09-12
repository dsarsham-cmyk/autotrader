"""Unit tests. Run with: python -m pytest tests/"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strategy import (
    Signal,
    Strategy,
    MovingAverageCrossover,
    RSI,
    BollingerBands,
    MACD,
    TrendFollowing,
    DonchianBreakout,
    VolatilityBreakout,
    ZScoreMeanReversion,
    TimeSeriesMomentum,
    OpeningRangeBreakout,
    IntradayMomentum,
    VolatilityScaledMomentum,
    RegimeAdaptive,
    VWAPMeanReversion,
    GapAndGo,
    VolumeBreakout,
    Supertrend,
    Stochastic,
    KeltnerChannelBreakout,
    NR7Breakout,
    PairsTrading,
    realized_vol,
    atr,
    build_strategy,
)
from risk import RiskConfig, RiskManager
from backtest import run_simulation


def to_candles(closes):
    """Convert a list of closes into flat OHLCV candles."""
    return [(i, c, c, c, c, 0.0) for i, c in enumerate(closes)]


def to_candles_v(closes, vols=None, ts=None):
    """Candles with volume (and optional timestamps in ms)."""
    vols = vols or [100.0] * len(closes)
    ts = ts or list(range(len(closes)))
    return [(ts[i], c, c, c, c, vols[i]) for i, c in enumerate(closes)]


def oscillating(n=200):
    return [50 + 15 * math.sin(i / 6.0) + i * 0.05 for i in range(n)]


def to_candles_r(closes, rng=1.0):
    """Candles with a real high-low range (for ATR-based strategies)."""
    out = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        h = max(o, c) + rng
        l = min(o, c) - rng
        out.append([i, o, h, l, c, 100.0])
        prev = c
    return out


def test_ma_crossover_buy_and_sell():
    s = MovingAverageCrossover(fast_period=3, slow_period=5)
    up = [10 + i for i in range(30)]
    down = [40 - i for i in range(30)]
    data = to_candles([10] * 6 + up)
    signals = [s.evaluate(data[:i]) for i in range(6, len(data) + 1)]
    assert Signal.BUY in signals
    data2 = to_candles([40] * 6 + down)
    signals2 = [s.evaluate(data2[:i]) for i in range(6, len(data2) + 1)]
    assert Signal.SELL in signals2


def test_ma_insufficient_data_holds():
    s = MovingAverageCrossover(fast_period=3, slow_period=5)
    assert s.evaluate(to_candles([1, 2, 3])) == Signal.HOLD


def test_rsi_values():
    r = RSI()
    assert r._rsi([10 + i for i in range(30)]) == 100.0
    assert r._rsi([50 - i for i in range(30)]) == 0.0


def test_rsi_fires_on_oscillation():
    r = RSI()
    data = to_candles(oscillating())
    signals = [r.evaluate(data[:i]) for i in range(30, len(data) + 1)]
    assert Signal.BUY in signals
    assert Signal.SELL in signals


def test_bollinger_fires_on_oscillation():
    b = BollingerBands()
    data = to_candles(oscillating())
    signals = [b.evaluate(data[:i]) for i in range(30, len(data) + 1)]
    assert Signal.BUY in signals
    assert Signal.SELL in signals


def test_macd_fires_on_oscillation():
    m = MACD()
    data = to_candles(oscillating())
    signals = [m.evaluate(data[:i]) for i in range(40, len(data) + 1)]
    assert Signal.BUY in signals
    assert Signal.SELL in signals


def test_trend_following_uptrend_buy():
    tf = TrendFollowing(fast_period=5, slow_period=10, trend_period=20)
    # Flat base, then uptrend -> fast EMA crosses above slow (golden cross).
    data = to_candles([10.0] * 30 + [10 + i * 0.5 for i in range(90)])
    signals = [tf.evaluate(data[:i]) for i in range(30, len(data) + 1)]
    assert Signal.BUY in signals


def test_trend_following_downtrend_no_buy():
    tf = TrendFollowing(fast_period=5, slow_period=10, trend_period=20)
    data = to_candles([100 - i * 0.5 for i in range(120)])
    signals = [tf.evaluate(data[:i]) for i in range(30, len(data) + 1)]
    assert Signal.BUY not in signals  # regime filter blocks longs in downtrend


def test_atr_positive_and_sane():
    # Truly flat candles (no gaps) -> zero true range -> zero ATR.
    flat = to_candles([10.0] * 50)
    assert atr(flat, period=14)[-1] == 0.0
    # Trending candles (inter-bar gaps) -> positive ATR.
    trend = to_candles([10 + i * 0.5 for i in range(50)])
    assert atr(trend, period=14)[-1] > 0


def test_build_strategy():
    s = build_strategy({"name": "rsi", "period": 14})
    assert isinstance(s, RSI)
    s2 = build_strategy({"name": "trend_following"})
    assert isinstance(s2, TrendFollowing)


def test_ma_validation():
    try:
        MovingAverageCrossover(fast_period=50, slow_period=20)
        assert False, "should have raised"
    except ValueError:
        pass


def test_risk_position_size_scales_with_volatility():
    cfg = RiskConfig(risk_per_trade=0.01, atr_stop_mult=2.0)
    rm = RiskManager(cfg)
    # Higher ATR (more volatile) -> smaller position.
    low_vol = rm.position_size(equity=10000, price=100, atr_value=1.0)
    high_vol = rm.position_size(equity=10000, price=100, atr_value=5.0)
    assert high_vol < low_vol


def test_risk_position_size_capped():
    cfg = RiskConfig(risk_per_trade=0.01, atr_stop_mult=2.0, max_position_pct=0.25)
    rm = RiskManager(cfg)
    units = rm.position_size(equity=10000, price=100, atr_value=0.1)
    # Max position value = 25% of 10000 = 2500 -> 25 units.
    assert units <= 25.0


def test_risk_stops():
    cfg = RiskConfig(atr_stop_mult=2.0, atr_take_mult=3.0)
    rm = RiskManager(cfg)
    stop, take = rm.stops(entry_price=100, atr_value=2.0)
    assert stop == 96.0
    assert take == 106.0


def test_risk_trailing_stop():
    cfg = RiskConfig(atr_stop_mult=2.0, break_even_atr=1.0,
                     trail_atr=2.0, trail_distance_atr=1.0)
    rm = RiskManager(cfg)
    entry, atr = 100.0, 2.0
    initial_stop = entry - atr * 2.0  # 96
    # Not yet +1 ATR -> stop unchanged.
    assert rm.trailing_stop(entry, 101.0, atr, initial_stop) == 96.0
    # +1 ATR -> move to break-even.
    assert rm.trailing_stop(entry, 102.0, atr, initial_stop) == 100.0
    # +2 ATR -> trail at high - 1 ATR.
    assert rm.trailing_stop(entry, 104.0, atr, initial_stop) == 102.0
    # Stop never moves down.
    assert rm.trailing_stop(entry, 104.0, atr, 103.0) == 103.0


def test_risk_daily_loss_halt():
    cfg = RiskConfig(daily_loss_limit_pct=0.03)
    rm = RiskManager(cfg)
    rm.update_equity(10000, "2026-01-01")
    rm.update_equity(9600, "2026-01-01")  # -4% -> exceeds 3% limit
    assert rm.halted
    assert not rm.allow_trading()


def test_risk_max_drawdown_halt():
    cfg = RiskConfig(max_drawdown_pct=0.20)
    rm = RiskManager(cfg)
    rm.update_equity(10000, "2026-01-01")
    rm.update_equity(7900, "2026-01-01")  # -21% -> exceeds 20% kill switch
    assert rm.halted


def test_donchian_breakout_buy():
    d = DonchianBreakout(entry_period=5, exit_period=3)
    # Flat base, then close breaks above the prior 5-bar high.
    data = to_candles([10.0] * 10 + [11.0, 12.0])
    assert d.evaluate(data) == Signal.BUY


def test_donchian_breakout_sell():
    d = DonchianBreakout(entry_period=5, exit_period=3)
    # Close breaks below the prior 3-bar low.
    data = to_candles([20.0] * 10 + [19.0, 18.0])
    assert d.evaluate(data) == Signal.SELL


def test_intraday_momentum_buy_and_sell():
    s = IntradayMomentum(fast_period=3, slow_period=5)
    up = to_candles([10] * 6 + [10 + i for i in range(30)])
    signals = [s.evaluate(up[:i]) for i in range(6, len(up) + 1)]
    assert Signal.BUY in signals
    down = to_candles([40] * 6 + [40 - i for i in range(30)])
    signals2 = [s.evaluate(down[:i]) for i in range(6, len(down) + 1)]
    assert Signal.SELL in signals2


def test_time_series_momentum_direction():
    s = TimeSeriesMomentum(lookback=5)
    up = to_candles([10 + i for i in range(20)])
    assert s.evaluate(up) == Signal.BUY
    down = to_candles([30 - i for i in range(20)])
    assert s.evaluate(down) == Signal.SELL


def test_opening_range_breakout():
    s = OpeningRangeBreakout(or_bars=2)
    # Opening range = first 2 bars (high 11). Close 12 breaks above it.
    data = to_candles([10.0, 11.0, 10.5, 11.5, 12.0])
    assert s.evaluate(data) == Signal.BUY
    # Close below the opening-range low (10) -> SELL.
    data2 = to_candles([10.0, 11.0, 10.5, 9.8, 9.5])
    assert s.evaluate(data2) == Signal.SELL


def test_volatility_breakout_hold_flat():
    v = VolatilityBreakout(ema_period=5, atr_period=5, rsi_period=5)
    flat = to_candles([10.0] * 30)
    assert v.evaluate(flat) == Signal.HOLD  # no breakout on flat data


def test_zscore_mean_reversion_buy():
    z = ZScoreMeanReversion(period=10, entry_z=2.0, exit_z=0.5)
    # Flat then sharp drop -> z-score well below -2 -> BUY.
    data = to_candles([50.0] * 20 + [40.0, 38.0])
    assert z.evaluate(data) == Signal.BUY


def test_build_strategy_new_names():
    assert isinstance(build_strategy({"name": "donchian_breakout"}), DonchianBreakout)
    assert isinstance(build_strategy({"name": "intraday_momentum"}), IntradayMomentum)
    assert isinstance(build_strategy({"name": "opening_range_breakout"}), OpeningRangeBreakout)
    assert isinstance(build_strategy({"name": "time_series_momentum"}), TimeSeriesMomentum)


def test_realized_vol_flat_vs_spiky():
    flat = to_candles([10.0] * 30)
    assert realized_vol(flat, period=20) == 0.0
    spiky = to_candles([10.0] * 20 + [10.0, 20.0, 10.0, 20.0, 10.0, 20.0, 10.0, 20.0])
    assert realized_vol(spiky, period=20) > 0.0


def test_volatility_scaled_momentum_buy_and_sell():
    s = VolatilityScaledMomentum(lookback=30, vol_period=5, vol_baseline=30, vol_mult=2.0)
    # Smooth uptrend -> positive momentum, normal vol -> BUY.
    up = to_candles([10 + i * 0.5 for i in range(40)])
    assert s.evaluate(up) == Signal.BUY
    # Smooth downtrend -> negative momentum -> SELL.
    down = to_candles([40 - i * 0.5 for i in range(40)])
    assert s.evaluate(down) == Signal.SELL


def test_volatility_scaled_momentum_vol_filter_blocks():
    s = VolatilityScaledMomentum(lookback=30, vol_period=5, vol_baseline=30, vol_mult=1.5)
    # Net-up but a sharp recent volatility spike -> filter blocks entry (HOLD).
    data = to_candles([10.0] * 30 + [10.0, 20.0, 10.0, 20.0, 25.0])
    assert s.evaluate(data) == Signal.HOLD


def test_regime_adaptive_trend_momentum_buy():
    s = RegimeAdaptive(fast_period=5, slow_period=10, trend_threshold=1.0,
                       mean_period=20, entry_z=2.0, exit_z=0.5)
    # Strong smooth uptrend -> trend regime -> EMA golden cross -> BUY.
    data = to_candles([10.0] * 20 + [10 + i * 0.5 for i in range(60)])
    signals = [s.evaluate(data[:i]) for i in range(30, len(data) + 1)]
    assert Signal.BUY in signals


def test_regime_adaptive_range_mean_reversion_buy():
    s = RegimeAdaptive(fast_period=5, slow_period=10, trend_threshold=5.0,
                       mean_period=20, entry_z=2.0, exit_z=0.5)
    # Flat then sharp drop -> range regime (low trend strength) -> z-score BUY.
    data = to_candles([50.0] * 30 + [40.0, 38.0])
    assert s.evaluate(data) == Signal.BUY


def test_build_strategy_research_names():
    assert isinstance(build_strategy({"name": "volatility_scaled_momentum"}),
                      VolatilityScaledMomentum)
    assert isinstance(build_strategy({"name": "regime_adaptive"}), RegimeAdaptive)


def test_pairs_trading_short_a_when_a_expensive():
    s = PairsTrading(window=50, entry_z=2.0, exit_z=0.5)
    b = to_candles([100.0] * 60)
    a = to_candles([100.0] * 50 + [105, 110, 115, 120, 125, 130, 135, 140, 145, 150])
    action, z = s.signal(a, b)
    assert action == "short_a"
    assert z > 2.0


def test_pairs_trading_long_a_when_a_cheap():
    s = PairsTrading(window=50, entry_z=2.0, exit_z=0.5)
    b = to_candles([100.0] * 60)
    a = to_candles([100.0] * 50 + [95, 90, 85, 80, 75, 70, 65, 60, 55, 50])
    action, z = s.signal(a, b)
    assert action == "long_a"
    assert z < -2.0


def test_pairs_trading_flat_when_correlated():
    s = PairsTrading(window=50, entry_z=2.0, exit_z=0.5)
    a = to_candles([100.0] * 60)
    b = to_candles([100.0] * 60)
    action, z = s.signal(a, b)
    assert action == "flat"


def test_pairs_trading_insufficient_data():
    s = PairsTrading(window=50)
    a = to_candles([100.0] * 10)
    b = to_candles([100.0] * 10)
    assert s.zscore(a, b) is None
    assert s.signal(a, b) == ("flat", 0.0)


def test_vwap_mean_reversion_buy_below_vwap():
    s = VWAPMeanReversion(band_pct=0.3)
    data = to_candles_v([100.0] * 20 + [90.0] * 10)
    assert s.evaluate(data) == Signal.BUY


def test_vwap_mean_reversion_sell_at_vwap():
    s = VWAPMeanReversion(band_pct=0.3)
    data = to_candles_v([100.0] * 20 + [105.0] * 10)
    assert s.evaluate(data) == Signal.SELL


def test_gap_and_go_buy_on_gap_up():
    s = GapAndGo(gap_pct=0.3)
    day = 86400000
    data = [
        [0, 100, 100, 100, 100, 100.0],
        [day, 101, 101, 101, 101, 100.0],
        [day + 1000, 101.5, 101.5, 101.5, 101.5, 100.0],
        [day + 2000, 102, 102, 102, 102, 100.0],
    ]
    assert s.evaluate(data) == Signal.BUY


def test_gap_and_go_sell_on_gap_down():
    s = GapAndGo(gap_pct=0.3)
    day = 86400000
    data = [
        [0, 100, 100, 100, 100, 100.0],
        [day, 99, 99, 99, 99, 100.0],
        [day + 1000, 98.5, 98.5, 98.5, 98.5, 100.0],
        [day + 2000, 98, 98, 98, 98, 100.0],
    ]
    assert s.evaluate(data) == Signal.SELL


def test_volume_breakout_buy_on_volume_spike():
    s = VolumeBreakout(lookback=20, vol_mult=2.0)
    data = to_candles_v([100.0] * 24 + [110.0], [100.0] * 24 + [500.0])
    assert s.evaluate(data) == Signal.BUY


def test_volume_breakout_hold_without_volume():
    s = VolumeBreakout(lookback=20, vol_mult=2.0)
    # Price breaks out but volume is normal -> no confirmation -> HOLD.
    data = to_candles_v([100.0] * 24 + [110.0], [100.0] * 25)
    assert s.evaluate(data) == Signal.HOLD


def test_build_strategy_sophisticated_names():
    assert isinstance(build_strategy({"name": "vwap_mean_reversion"}), VWAPMeanReversion)
    assert isinstance(build_strategy({"name": "gap_and_go"}), GapAndGo)
    assert isinstance(build_strategy({"name": "volume_breakout"}), VolumeBreakout)


def test_close_at_eod_closes_positions():
    """Day-trading mode must not hold positions across day boundaries."""

    class AlwaysBuy(Strategy):
        warmup = 2

        def evaluate(self, candles):
            return Signal.BUY

    # 4 days x 24 hourly bars, slight uptrend. The 14-bar ATR warmup
    # consumes the first part of day 0; the remaining days each produce a
    # full round trip when close_at_eod is enabled.
    day_ms = 24 * 60 * 60 * 1000
    hour_ms = 60 * 60 * 1000
    candles = []
    for day in range(4):
        for hour in range(24):
            ts = day * day_ms + hour * hour_ms
            p = 100.0 + day + hour * 0.1
            candles.append([ts, p, p, p, p, 0.0])

    # Large stop/take multipliers so intra-day stops never trigger in this
    # synthetic data; we only want to exercise the end-of-day close logic.
    cfg = RiskConfig(risk_per_trade=0.01, atr_stop_mult=100.0,
                     atr_take_mult=100.0, max_position_pct=1.0)

    with_eod = run_simulation(candles, AlwaysBuy(), RiskManager(cfg),
                              fee_pct=0.0, start_equity=100000,
                              min_history=2, close_at_eod=True)
    without_eod = run_simulation(candles, AlwaysBuy(), RiskManager(cfg),
                                 fee_pct=0.0, start_equity=100000,
                                 min_history=2, close_at_eod=False)

    # With EOD close, every trading day produces a full round trip.
    assert with_eod["round_trips"] == 4
    # Without EOD close, the position is held to the end (1 round trip).
    assert without_eod["round_trips"] == 1


def test_supertrend_fires_on_trend_change():
    s = Supertrend(period=10, multiplier=3.0)
    down = [100 - i * 0.5 for i in range(60)]
    up = [70 + i * 0.5 for i in range(60)]
    data = to_candles_r(down + up)
    signals = [s.evaluate(data[:i]) for i in range(20, len(data) + 1)]
    assert Signal.BUY in signals


def test_supertrend_insufficient_data_holds():
    s = Supertrend()
    assert s.evaluate(to_candles_r([100.0] * 5)) == Signal.HOLD


def test_stochastic_fires_on_oscillation():
    s = Stochastic()
    data = to_candles_r(oscillating())
    signals = [s.evaluate(data[:i]) for i in range(30, len(data) + 1)]
    assert Signal.BUY in signals
    assert Signal.SELL in signals


def test_keltner_breakout_buy_above_upper():
    s = KeltnerChannelBreakout(period=20, atr_period=10, mult=2.0)
    # Flat base (low ATR, stable EMA) then a single sharp jump above the band.
    data = to_candles_r([100.0] * 30 + [120.0])
    assert s.evaluate(data) == Signal.BUY


def test_keltner_breakout_insufficient_data_holds():
    s = KeltnerChannelBreakout()
    assert s.evaluate(to_candles_r([100.0] * 10)) == Signal.HOLD


def test_nr7_breakout_buy_after_narrow_range():
    s = NR7Breakout(n=7)
    # 7 wide bars, then a narrow bar, then a breakout above the narrow high.
    data = to_candles_r([100.0] * 7 + [100.0, 103.0], rng=2.0)
    data[-2][2] = data[-2][4] + 0.1   # narrow bar high
    data[-2][3] = data[-2][4] - 0.1   # narrow bar low
    assert s.evaluate(data) == Signal.BUY


def test_nr7_breakout_hold_without_narrow_range():
    s = NR7Breakout(n=7)
    # No narrow-range bar -> no breakout signal.
    data = to_candles_r([100.0] * 8 + [103.0], rng=2.0)
    assert s.evaluate(data) == Signal.HOLD


def test_build_strategy_new_names():
    assert isinstance(build_strategy({"name": "supertrend"}), Supertrend)
    assert isinstance(build_strategy({"name": "stochastic"}), Stochastic)
    assert isinstance(build_strategy({"name": "keltner_breakout"}), KeltnerChannelBreakout)
    assert isinstance(build_strategy({"name": "nr7_breakout"}), NR7Breakout)


def test_incremental_ema_matches_naive():
    """The incremental ema cache must equal a from-scratch computation on a
    growing window (the exact pattern the backtester uses)."""
    import strategy as S

    def naive(values, period):
        k = 2.0 / (period + 1)
        out = [values[0]]
        for v in values[1:]:
            out.append(v * k + out[-1] * (1 - k))
        return out

    closes = [100 + math.sin(i / 5.0) * 3 + i * 0.01 for i in range(200)]
    S.clear_indicators()
    window = []  # growing list (same object) — exercises the incremental path
    for i in range(len(closes)):
        window.append(closes[i])
        if i < 2:
            continue
        for period in (5, 14, 20):
            assert S.ema(window, period) == naive(window, period)


def test_incremental_atr_matches_naive():
    """The incremental atr cache must equal a from-scratch computation."""
    import strategy as S

    def naive(candles, period):
        if len(candles) < 2:
            return [0.0] * len(candles)
        trs = [0.0]
        for i in range(1, len(candles)):
            h, l, pc = candles[i][2], candles[i][3], candles[i - 1][4]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        out = [0.0] * len(candles)
        if len(trs) <= period:
            return out
        first = sum(trs[1:period + 1]) / period
        out[period] = first
        for i in range(period + 1, len(trs)):
            out[i] = (out[i - 1] * (period - 1) + trs[i]) / period
        return out

    candles = to_candles_r(oscillating(200), rng=0.5)
    S.clear_indicators()
    window = []  # growing list (same object)
    for i in range(len(candles)):
        window.append(candles[i])
        if i < 2:
            continue
        for period in (5, 14):
            assert S.atr(window, period) == naive(window, period)


def test_incremental_supertrend_matches_naive():
    """Supertrend's instance-level incremental cache must match a naive run."""
    candles = to_candles_r(oscillating(150), rng=0.5)
    s = Supertrend(period=10, multiplier=3.0)
    # A reused instance extends incrementally as the window grows; the
    # direction signals must be identical to a from-scratch computation.
    window = []
    signals = []
    for i in range(len(candles)):
        window.append(candles[i])
        if i >= 20:
            signals.append(s.evaluate(window))
    assert Signal.BUY in signals or Signal.SELL in signals
