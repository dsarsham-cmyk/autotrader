from datetime import datetime, timezone
from account_history import build_history, compact_executions
from test_daily_pnl import fill

NOW = datetime(2026, 9, 22, 18, tzinfo=timezone.utc)


def stamp(day):
    return int(datetime(2026, 9, day, 20, tzinfo=timezone.utc).timestamp())


def base():
    return {"raw": {"timestamp": [stamp(16), stamp(17), stamp(18), stamp(21)],
                    "equity": [0, 100000, 100100, 100050],
                    # Deliberately cumulative: must not be presented as daily.
                    "profit_loss": [0, 0, 100, 50]},
            "activities": [], "fetched_at": NOW.isoformat(),
            "coverage_start": "2026-08-21"}


def test_history_daily_differences_and_no_funding_profit():
    out = build_history(base(), [], {"equity": 100070, "day_pnl": 20,
                                     "day_pnl_pct": .02}, NOW, True)
    days = {x["date"]: x for x in out["days"]}
    assert "2026-09-16" not in days
    assert days["2026-09-17"]["day_change"] is None
    assert days["2026-09-18"]["day_change"] == 100
    assert days["2026-09-21"]["day_change"] == -50
    assert days["2026-09-22"]["day_change"] == 20
    assert days["2026-09-22"]["status"] == "intraday"
    assert days["2026-09-21"]["execution_count"] == 0
    assert "2026-09-19" not in days  # no invented Saturday


def test_missing_today_executions_are_not_zero():
    out = build_history(base(), None, {"equity": 100070}, NOW, True)
    assert out["days"][0]["execution_count"] is None


def test_partial_fills_preserve_actual_qty_price_and_count():
    acts = [fill("1", "QQQ", "sell", 2, 100, order_id="same", cum_qty="2"),
            fill("2", "QQQ", "sell", 3, 101, order_id="same", cum_qty="5")]
    compact = compact_executions(acts + [acts[0]])
    assert len(compact) == 2
    assert sum(x["qty"] for x in compact) == 5
    assert sum(x["qty"] * x["price"] for x in compact) == 503
    out = build_history(base(), compact, {"equity": 100070}, NOW, True)
    assert out["days"][0]["execution_count"] == 2
    assert out["days"][0]["order_count"] == 1


def test_missing_equity_preserves_activity_without_invented_pnl():
    data = base()
    data["activities"] = [fill("1", "SPY", "buy", 1, 100,
                              transaction_time="2026-09-15T14:00:00Z")]
    out = build_history(data, [], {}, NOW, False)
    row = next(x for x in out["days"] if x["date"] == "2026-09-15")
    assert row["day_change"] is None
    assert row["execution_count"] == 1
    assert row["status"] == "missing_equity"


def test_missing_equity_breaks_daily_baseline():
    data = base()
    data["raw"]["equity"] = [100000, None, 100100, 100050]
    out = build_history(data, [], {}, NOW, False)
    row = next(x for x in out["days"] if x["date"] == "2026-09-18")
    assert row["day_change"] is None
