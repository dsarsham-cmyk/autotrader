"""Synthetic broker-transition replays; never connect to a real broker."""
from copy import deepcopy
import json
import time

import safe_paper_engine as engine
from test_paper_safety import setup, position, stop
from test_execution_recovery import partial


def test_policy_cause_survives_generic_completion_and_restart(setup):
    e, api = setup
    api.account["equity"] = "99000"
    status = e.tick()
    assert status["reason"] == "liquidation confirmed; no re-entry today"
    assert status["liquidation_cause"]["reason"] == "daily loss exit"
    assert status["liquidation_cause"]["completed_at"]
    saved = deepcopy(status["liquidation_cause"])
    restored = engine.Engine(api, e.configs, e.signals, json.loads(engine.STATE.read_text()))
    api.account["equity"] = "100000"
    restored.tick()
    assert restored.status["liquidation_cause"] == saved
    assert restored.state["entry_blocked"]
    assert not api.submitted


def test_timeout_cascade_records_failing_and_protected_symbols(setup):
    e, api = setup
    partial(api, e)
    # Synthetic equivalent of a failing bracket recovery alongside an already
    # protected holding. Do not claim this proves the historical broker cause.
    api.positions.append(position("SPXL", "22"))
    api.open.append(stop("SPXL", "22"))
    e.tick()
    assert not e.state.get("liquidating")
    e.state["protection_repairs"]["TQQQ"]["started_at"] = time.time()-31
    e.persist()
    restored = engine.Engine(api, e.configs, e.signals, json.loads(engine.STATE.read_text()))
    status = restored.tick()
    cause = deepcopy(status["liquidation_cause"])
    assert cause["reason"] == "broker protection missing or unverified"
    assert cause["fatal_protection_symbols"] == ["TQQQ"]
    assert cause["verified_stop_symbols"] == ["SPXL"]
    assert cause["position_symbols"] == ["SPXL", "TQQQ"]
    assert cause["protection_repairs"]["TQQQ"]["age_seconds"] >= 30
    assert cause["protection_repairs"]["TQQQ"]["phase"] == "canceling_conflicting_orders"
    # Existing global cascade is preserved: next cycle also cancels the other
    # holding's protection. Instrumentation must not silently change scope.
    restored.tick()
    assert "/v2/orders/stop-SPXL" in api.deleted
    assert restored.state["liquidation_cause"] == cause
    api.open = []
    restored.tick()
    assert {o["symbol"] for o in api.submitted if o["type"] == "market"} == {"TQQQ", "SPXL"}
    api.positions = []
    restored.tick()
    assert restored.status["reason"] == "liquidation confirmed; no re-entry today"
    assert restored.status["liquidation_cause"]["reason"] == cause["reason"]
    assert restored.status["liquidation_cause"]["completed_at"]
    assert len(restored.state["liquidation_history"]) == 1


def test_later_reason_cannot_replace_first_trigger(setup):
    e, api = setup
    api.positions = [position()]
    api.open = [stop()]
    api.account["equity"] = "99000"
    e.tick()
    first = deepcopy(e.state["liquidation_cause"])
    api.account["equity"] = "89000"
    e.tick()
    assert e.state["liquidating"] == "maximum drawdown"
    assert e.state["liquidation_cause"] == first
    assert first["reason"] == "daily loss exit"


def test_legacy_liquidation_does_not_invent_original_trigger_time(setup):
    e, api = setup
    e.state["liquidating"] = "broker protection missing or unverified"
    e.tick()
    cause = e.status["liquidation_cause"]
    assert cause["origin"] == "policy_or_restored_state"
    assert "triggered_at" not in cause
    assert cause["fatal_protection_symbols"] == []
    assert cause["completed_at"]


def test_persistent_loss_condition_does_not_duplicate_completed_event(setup):
    e, api = setup
    api.account["equity"] = "99000"
    e.tick()
    first = deepcopy(e.status["liquidation_cause"])
    e.tick()
    e.tick()
    assert e.status["liquidation_cause"] == first
    assert len(e.state["liquidation_history"]) == 1
    assert not api.submitted
