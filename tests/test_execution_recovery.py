import json
import time

import pytest
import requests

import safe_paper_engine as engine
from paper_safety import stop_coverage
from test_paper_safety import setup, position, stop


def partial(api, e):
    api.positions = [position(qty="8")]
    api.open = [{
        "id": "parent", "symbol": "TQQQ", "side": "buy", "type": "limit",
        "order_class": "bracket", "status": "partially_filled",
        "client_order_id": engine.identity("entry", e.state["day"], "TQQQ"),
        "qty": "62", "filled_qty": "8",
        "legs": [stop(qty="62", status="held"),
                 {"id": "take", "symbol": "TQQQ", "side": "sell", "type": "limit",
                  "limit_price": "120", "qty": "62", "status": "held"}],
    }]


def cancel_immediately(api, monkeypatch, late_qty=None):
    original = api.call
    def call(method, path, **kwargs):
        result = original(method, path, **kwargs)
        if method == "DELETE":
            api.open = []
            if late_qty:
                api.positions = [position(qty=late_qty)]
        return result
    monkeypatch.setattr(api, "call", call)
    submit = api.submit_once
    def placed(payload):
        order = submit(payload)
        if payload["type"] == "stop":
            api.open = [dict(order, filled_qty="0")]
        return order
    monkeypatch.setattr(api, "submit_once", placed)


def test_partial_retained_with_verified_stop_for_actual_fill(setup, monkeypatch):
    e, api = setup
    partial(api, e)
    cancel_immediately(api, monkeypatch)
    e.tick()
    assert api.deleted == ["/v2/orders/parent"]
    assert len(api.submitted) == 1
    p = api.submitted[0]
    assert p["side"] == "sell" and p["type"] == "stop"
    assert float(p["qty"]) == 8 and p["stop_price"] == 90
    assert stop_coverage(api.positions[0], api.open)
    assert not e.state.get("liquidating") and not e.state.get("entry_blocked")
    e.tick()
    assert len(api.submitted) == 1


def test_late_fills_during_cancel_are_included_in_stop_quantity(setup, monkeypatch):
    e, api = setup
    partial(api, e)
    cancel_immediately(api, monkeypatch, late_qty="11")
    e.tick()
    assert float(api.submitted[0]["qty"]) == 11
    assert stop_coverage(api.positions[0], api.open)


def test_cancel_wait_blocks_entries_without_liquidating(setup):
    e, api = setup
    partial(api, e)
    status = e.tick()
    assert not api.submitted
    assert status["entry_blocked"] and status["protection_repairing"]
    assert not e.state.get("liquidating")
    assert status["verified_stops"] == 0


def test_cancel_deadline_falls_back_to_exit_and_survives_restart(setup):
    e, api = setup
    partial(api, e)
    e.tick()
    e.state["protection_repairs"]["TQQQ"]["started_at"] = time.time()-31
    e.persist()
    restored = engine.Engine(api, e.configs, e.signals, json.loads(engine.STATE.read_text()))
    restored.tick()
    assert restored.state["liquidating"] == "broker protection missing or unverified"
    api.open = []
    restored.tick()
    assert api.submitted[-1]["type"] == "market" and api.submitted[-1]["side"] == "sell"


def test_rejected_protective_stop_falls_back_to_exit(setup, monkeypatch):
    e, api = setup
    partial(api, e)
    cancel_immediately(api, monkeypatch)
    api.result_status = "rejected"
    e.tick()
    assert e.state["liquidating"]
    assert e.state["entry_blocked"]


def test_full_bracket_with_active_stop_kept_intact(setup):
    e, api = setup
    api.positions = [position(qty="8")]
    api.open = [stop(qty="8")]
    e.tick()
    assert not api.deleted and not api.submitted
    assert e.status["verified_stops"] == 1


def full_fill(api, e, monkeypatch, qty="8"):
    partial(api, e)
    parent = dict(api.open[0], status="filled", qty=qty, filled_qty=qty)
    api.positions = [position(qty=qty)]
    parent["legs"][0]["qty"] = qty
    parent["legs"][1]["qty"] = qty
    # Real OPEN inventories omit the filled entry; take-profit roots the group.
    take = dict(parent["legs"][1], status="new", legs=[parent["legs"][0]])
    api.open = [take]
    e.state["attempted"] = ["TQQQ"]
    original = api.call
    expected = parent["client_order_id"]
    def call(method, path, **kwargs):
        if path == "/v2/orders:by_client_order_id":
            assert method == "GET"
            assert kwargs["params"]["client_order_id"] == expected
            return parent
        return original(method, path, **kwargs)
    monkeypatch.setattr(api, "call", call)
    return parent


def test_full_fill_held_nested_stop_converted_not_falsely_verified(setup, monkeypatch):
    e, api = setup
    full_fill(api, e, monkeypatch)
    assert not stop_coverage(api.positions[0], api.open)
    cancel_immediately(api, monkeypatch)
    e.tick()
    assert api.deleted == ["/v2/orders/take"]
    assert len(api.submitted) == 1
    assert api.submitted[0]["type"] == "stop"
    assert float(api.submitted[0]["qty"]) == 8
    assert stop_coverage(api.positions[0], api.open)
    assert not e.state.get("liquidating")
    e.tick()
    assert e.status["verified_stops"] == 1
    assert len(api.submitted) == 1


def test_full_fill_unverified_cancel_is_bounded_across_restart(setup, monkeypatch):
    e, api = setup
    full_fill(api, e, monkeypatch)
    e.tick()
    assert e.status["protection_repairing"] and not api.submitted
    e.state["protection_repairs"]["TQQQ"]["started_at"] = time.time()-31
    e.persist()
    restored = engine.Engine(api, e.configs, e.signals, json.loads(engine.STATE.read_text()))
    restored.tick()
    assert restored.state["liquidating"] == "broker protection missing or unverified"


@pytest.mark.parametrize("change", [{"side": "sell"}, {"status": "new"},
    {"filled_qty": "0"}, {"filled_qty": "3"}, {"client_order_id": "other"},
    {"symbol": "SPY"}, {"order_class": "simple"}])
def test_full_fill_recovery_refuses_unproven_parent(setup, monkeypatch, change):
    e, api = setup
    parent = full_fill(api, e, monkeypatch)
    parent.update(change)
    e.tick()
    assert e.state.get("liquidating")
    assert not any(p["type"] == "stop" for p in api.submitted)


def test_full_fill_standalone_stop_then_strategy_exit(setup, monkeypatch):
    e, api = setup
    full_fill(api, e, monkeypatch)
    cancel_immediately(api, monkeypatch)
    e.tick()
    e.signals["TQQQ"]["signal"] = "sell"
    e.tick()
    e.tick()
    assert api.submitted[-1]["type"] == "market"
    assert api.submitted[-1]["side"] == "sell"


def test_partial_take_profit_preserved_after_conversion(setup, monkeypatch):
    e, api = setup
    partial(api, e)
    cancel_immediately(api, monkeypatch)
    e.tick()
    api.bid = 121
    e.tick()
    assert e.state["exit_intents"]["TQQQ"] == "take-profit exit"


def test_daily_liquidation_takes_priority_over_partial_repair(setup):
    e, api = setup
    partial(api, e)
    api.account["equity"] = 99000
    e.tick()
    assert e.state["liquidating"] == "daily loss exit"
    assert not e.state.get("protection_repairs")


def test_read_timeout_recovers_after_two_complete_reads(setup):
    e, api = setup
    e.handle_failure(requests.exceptions.ReadTimeout("temporary read"))
    assert e.status["entry_blocked"] and e.state["connection_pause"]
    assert not e.state.get("entry_blocked")
    e.tick()
    assert e.status["entry_blocked"] and not api.submitted
    e.tick()
    assert not e.state.get("connection_pause")
    assert not e.status["entry_blocked"]
    assert len(api.submitted) == 1


def test_another_read_failure_restarts_recovery_count(setup):
    e, api = setup
    e.handle_failure(requests.exceptions.ReadTimeout("read"))
    e.tick()
    e.handle_failure(requests.exceptions.ReadTimeout("read again"))
    e.tick()
    assert not api.submitted and e.state["recovery_checks"] == 1


def test_transient_recovery_does_not_clear_daily_loss_latch(setup):
    e, api = setup
    api.account["equity"] = 99400
    e.tick()
    e.handle_failure(requests.exceptions.ReadTimeout("read"))
    api.account["equity"] = 100000
    e.tick()
    e.tick()
    assert e.state["entry_blocked"] and not api.submitted
    assert e.state["entry_reason"] == "daily entry cutoff"


def test_recovery_pause_survives_restart(setup):
    e, api = setup
    e.handle_failure(requests.exceptions.ReadTimeout("read"))
    restored = engine.Engine(api, e.configs, e.signals, json.loads(engine.STATE.read_text()))
    restored.tick()
    assert not api.submitted
    restored.tick()
    assert len(api.submitted) == 1


def test_uncertain_write_is_not_auto_cleared(setup):
    e, api = setup
    e.operation_stage = "write"
    e.handle_failure(requests.exceptions.ReadTimeout("uncertain submission"))
    e.tick()
    e.tick()
    assert e.state["entry_blocked"] and not api.submitted


def test_stop_accepted_then_response_lost_is_reconciled_without_duplicate(setup, monkeypatch):
    e, api = setup
    partial(api, e)
    cancel_immediately(api, monkeypatch)
    submit = api.submit_once
    def lose_response(payload):
        submit(payload)
        raise requests.exceptions.ReadTimeout("response lost after acceptance")
    monkeypatch.setattr(api, "submit_once", lose_response)
    with pytest.raises(requests.exceptions.ReadTimeout):
        e.tick()
    e.handle_failure(requests.exceptions.ReadTimeout("uncertain write"))
    monkeypatch.setattr(api, "submit_once", submit)
    e.tick()
    assert len(api.submitted) == 1
    assert e.status["verified_stops"] == 1
    assert e.state["partial_take_prices"]["TQQQ"] == 120
    assert not e.state["protection_repairs"]
    assert e.state["entry_blocked"]  # uncertainty did not unlock entries


@pytest.mark.parametrize("code", [429, 500, 503])
def test_transient_http_reads_can_recover(setup, code):
    e, api = setup
    e.handle_failure(engine.APIError("GET", "/v2/account", code))
    e.tick()
    e.tick()
    assert len(api.submitted) == 1


def test_authentication_failure_stays_blocked(setup):
    e, api = setup
    e.handle_failure(engine.APIError("GET", "/v2/account", 401))
    e.tick()
    e.tick()
    assert not api.submitted and e.state["entry_blocked"]
