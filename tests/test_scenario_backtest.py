from risk import RiskConfig
from strategy import Signal

import scenario_backtest


class _Signals:
    def __init__(self):
        self.calls = 0

    def evaluate(self, _candles):
        self.calls += 1
        return Signal.BUY if self.calls == 1 else Signal.HOLD


def test_trailing_stop_uses_bar_high_without_same_bar_lookahead(monkeypatch):
    monkeypatch.setattr(scenario_backtest, "build_strategy", lambda _cfg: _Signals())
    monkeypatch.setattr(scenario_backtest, "atr", lambda _candles, _period: [10.0])

    candles = {
        "TEST": [
            [1_700_000_000_000, 100.0, 101.0, 99.0, 100.0, 1_000.0],
            # The high activates a 111 stop, but today's low must not fill a
            # stop that did not exist until later in an unordered OHLC bar.
            [1_700_086_400_000, 105.0, 121.0, 100.0, 110.0, 1_000.0],
            [1_700_172_800_000, 110.0, 112.0, 110.0, 109.0, 1_000.0],
        ]
    }
    rc = RiskConfig(
        atr_stop_mult=2.0,
        atr_take_mult=100.0,
        break_even_atr=1.0,
        trail_atr=2.0,
        trail_distance_atr=1.0,
    )

    result = scenario_backtest.run_portfolio(
        candles, {"name": "unused"}, rc, fee_pct=0.0, start_equity=100_000.0
    )

    assert result["round_trips"] == 1
    assert result["per_symbol_pnl"]["TEST"] == 550.0
