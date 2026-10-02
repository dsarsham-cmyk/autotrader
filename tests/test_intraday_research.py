import pandas as pd
import pytest

from intraday_research import sessions, simulate, exit_price, metrics


def day(date, volume=100):
    index = pd.date_range(date+" 09:30", periods=390, freq="min", tz="America/New_York")
    return pd.DataFrame(dict(symbol="QQQ", open=100., high=101., low=99.,
                             close=100., volume=volume), index=index)


def test_missing_minutes_are_not_filled_or_invented():
    frame = day("2026-09-01").reset_index(names="timestamp").drop(index=10)
    valid, excluded = sessions(frame)
    assert not valid and excluded[0]["bars"] == 389


def test_invalid_bars_rejected():
    frame = day("2026-09-01").reset_index(names="timestamp")
    frame.loc[0, "low"] = 102
    with pytest.raises(ValueError):
        sessions(frame)


def test_gaps_and_ambiguous_bars_use_conservative_stop():
    assert exit_price(pd.Series(dict(open=90,low=89,high=105)),95,104) == (90., "stop")
    assert exit_price(pd.Series(dict(open=100,low=94,high=105)),95,104) == (95, "stop")


def test_entry_after_signal_no_leverage_and_one_trade():
    warmup = [(str(i),day("2026-09-01")) for i in range(20)]
    test = day("2026-09-02", volume=200)
    test.iloc[5, test.columns.get_loc("close")] = 102
    test.iloc[5, test.columns.get_loc("high")] = 103
    test.iloc[6:, test.columns.get_loc("high")] = 110
    rows, trades = simulate(warmup + [("2026-09-02",test)])
    assert len(trades) == 1
    trade = trades[0]
    assert pd.Timestamp(trade["entry_time"]) > pd.Timestamp(trade["signal_time"])
    assert trade["quantity"] * trade["entry"] <= 100000
    assert rows[-1]["pnl"] < 0  # stop and target touched; stop wins
    assert abs(rows[-1]["pnl"]) <= 200.01


def test_prefix_result_does_not_see_future_volume():
    days = [(str(i),day("2026-09-01",volume=100)) for i in range(25)]
    first, _ = simulate(days[:22])
    second, _ = simulate(days + [("future",day("2026-09-02",volume=100000))])
    assert first == second[:22]


def test_metric_cash_is_zero_return():
    assert metrics([dict(equity=100000,pnl=0,return_pct=0)],100000)["total_return_pct"] == 0


def test_gap_above_precomputed_limit_is_not_assumed_filled():
    warmup = [(str(i),day("2026-09-01")) for i in range(20)]
    frame = day("2026-09-02", volume=200)
    frame.iloc[5, frame.columns.get_loc("close")] = 102
    frame.iloc[6, frame.columns.get_loc("open")] = 104
    _, trades = simulate(warmup + [("last",frame)])
    assert not trades


def test_position_exits_before_close_when_stop_not_touched():
    warmup = [(str(i),day("2026-09-01")) for i in range(20)]
    frame = day("2026-09-02", volume=200)
    frame.iloc[5, frame.columns.get_loc("close")] = 102
    frame.iloc[6:, frame.columns.get_loc("open")] = 101
    frame.iloc[6:, frame.columns.get_loc("low")] = 100
    frame.iloc[6:, frame.columns.get_loc("high")] = 103
    _, trades = simulate(warmup + [("last",frame)])
    assert len(trades) == 1
    assert trades[0]["reason"] == "end_of_day"
    assert pd.Timestamp(trades[0]["exit_time"]).strftime("%H:%M") == "15:55"
