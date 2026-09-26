from datetime import datetime, timezone

from snapshot import build_audit


def _backtest():
    return {
        "high": {"profit_factor": 1.56, "sharpe": 0.82,
                 "max_drawdown_pct": 24.45, "annualized_return_pct": 12.98},
        "low": {"profit_factor": 1.37, "sharpe": 0.20,
                "max_drawdown_pct": 4.40, "annualized_return_pct": 0.68},
    }


def test_audit_detects_unprotected_positions_and_churn():
    fills = [
        {"time": "2026-09-17T14:00:00Z", "symbol": "SPY", "side": "sell"},
        {"time": "2026-09-17T14:05:00Z", "symbol": "SPY", "side": "buy"},
    ]
    recent_orders = [{
        "symbol": "SPY", "side": "buy", "type": "market",
        "order_class": "simple", "status": "filled", "legs": [],
    }]

    audit = build_audit(
        fills, _backtest(), {"SPY": {}}, [], recent_orders,
        datetime(2026, 9, 17, 18, 0, tzinfo=timezone.utc),
    )

    assert audit["good_enough"] is False
    assert audit["execution"]["churn_count"] == 1
    assert audit["execution"]["protected_positions"] == 0
    statuses = {item["key"]: item["status"] for item in audit["checks"]}
    assert statuses["risk_protection"] == "bad"
    assert statuses["execution_churn"] == "bad"


def test_audit_recognizes_active_stop_protection():
    open_orders = [{
        "id": "stop1", "qty": "1", "filled_qty": "0", "stop_price": "100",
        "symbol": "SPY", "side": "sell", "type": "stop",
        "order_class": "simple", "status": "new", "legs": [],
    }]

    audit = build_audit(
        [], _backtest(), {"SPY": {"qty": "1"}}, open_orders, [],
        datetime(2026, 9, 17, 18, 0, tzinfo=timezone.utc),
    )

    assert audit["execution"]["protected_positions"] == 1
    protection = next(item for item in audit["checks"]
                      if item["key"] == "risk_protection")
    assert protection["status"] == "good"
