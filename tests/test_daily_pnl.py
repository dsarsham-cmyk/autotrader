from datetime import datetime, timezone
import pytest
import daily_pnl
from daily_pnl import calculate_daily

NOW = datetime(2026, 9, 22, 18, tzinfo=timezone.utc)
META = {"high": {"symbols": ["AAA"]}, "low": {"symbols": ["BBB"]}}


def fill(ident, symbol, side, qty, price, **extra):
    return {"id": ident, "activity_type": "FILL", "symbol": symbol,
            "side": side, "qty": str(qty), "price": str(price),
            "transaction_time": "2026-09-22T14:00:00Z", **extra}


def test_overnight_hold_and_fully_closed_position():
    out = calculate_daily(META, {"AAA": {"qty": 10, "market_value": 1100}},
                          [fill("1", "BBB", "sell", 5, 22)],
                          {"AAA": 100, "BBB": 20}, 112, NOW)
    assert out["portfolios"]["high"]["day_pnl"] == 100
    assert out["portfolios"]["low"]["day_pnl"] == 10
    assert out["unallocated_day_pnl"] == 2


def test_partial_fills_not_cumulative_and_round_trip():
    trades = [fill("1", "AAA", "buy", 2, 10, cum_qty="2", order_id="same"),
              fill("2", "AAA", "buy", 3, 11, cum_qty="5", order_id="same"),
              fill("3", "AAA", "sell", 5, 12)]
    out = calculate_daily(META, {}, trades + [trades[0]], {}, 7, NOW)
    assert out["portfolios"]["high"]["day_pnl"] == 7
    assert out["buy_executions"] == 2
    assert out["unallocated_day_pnl"] == 0


def test_overnight_partial_sale_and_new_purchase():
    trades = [fill("1", "AAA", "sell", 4, 105), fill("2", "AAA", "buy", 2, 108)]
    out = calculate_daily(META, {"AAA": {"qty": 8, "market_value": 880}},
                          trades, {"AAA": 100}, 84, NOW)
    assert out["portfolios"]["high"]["day_pnl"] == 84
    assert out["portfolios"]["high"]["daily_symbols"][0]["start_qty"] == 10


def test_new_york_day_and_negative_return():
    prior = fill("1", "AAA", "buy", 100, 1,
                 transaction_time="2026-09-22T01:00:00Z")  # previous NY day
    out = calculate_daily(META, {"AAA": {"qty": 1, "market_value": 9}},
                          [prior], {"AAA": 10}, -1, NOW)
    assert out["portfolios"]["high"]["day_pnl"] == -1
    assert out["buy_executions"] == 0


def test_missing_baseline_is_not_zero():
    with pytest.raises(ValueError, match="Previous close"):
        calculate_daily(META, {"AAA": {"qty": 1, "market_value": 12}}, [], {}, 0, NOW)


def test_split_is_not_misreported_as_profit():
    with pytest.raises(ValueError, match="Corporate action"):
        calculate_daily(META, {}, [{"activity_type": "SPLIT", "symbol": "AAA"}],
                        {}, 0, NOW)


def test_overlapping_scenarios_rejected():
    with pytest.raises(ValueError, match="overlap"):
        calculate_daily({"a": {"symbols": ["AAA"]}, "b": {"symbols": ["AAA"]}},
                        {}, [], {}, 0, NOW)


def test_full_day_activity_pagination(monkeypatch):
    first = [fill(str(i), "AAA", "buy", 1, 1) for i in range(100)]
    urls = []
    def get(url, *_):
        urls.append(url)
        return first if len(urls) == 1 else [fill("100", "AAA", "sell", 1, 2)]
    monkeypatch.setattr(daily_pnl, "_get", get)
    assert len(daily_pnl.activities_today("key", "secret", NOW)) == 101
    assert "page_token=99" in urls[1]


def test_previous_close_excludes_today(monkeypatch):
    daily_pnl._CLOSE_CACHE.clear()
    monkeypatch.setattr(daily_pnl, "_get", lambda *_: {"bars": [
        {"t": "2026-09-22T04:00:00Z", "c": 999},
        {"t": "2026-09-21T04:00:00Z", "c": 100},
    ]})
    assert daily_pnl.previous_close("AAA", "key", "secret", NOW) == 100
