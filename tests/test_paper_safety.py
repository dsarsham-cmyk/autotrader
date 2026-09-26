from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import time

import pytest
import yaml
import safe_paper_engine as engine
from paper_safety import apply_policy, market_day, stop_coverage, entry_budget


def position(symbol="TQQQ", qty="2"):
    return {"symbol": symbol, "qty": qty, "market_value": str(float(qty)*100),
            "avg_entry_price": "100"}


def stop(symbol="TQQQ", qty="2", **extra):
    return dict({"id": "stop-"+symbol, "symbol": symbol, "qty": qty,
                 "filled_qty": "0", "side": "sell", "type": "stop",
                 "stop_price": "90", "status": "new"}, **extra)


class API:
    def __init__(self):
        now = datetime.now(timezone.utc)
        self.clock = {"timestamp": now.isoformat(), "is_open": True,
                      "next_close": (now+timedelta(hours=2)).isoformat()}
        self.account = {"equity": "100000", "last_equity": "100000", "cash": "100000"}
        self.positions = []
        self.open = []
        self.submitted = []
        self.deleted = []
        self.saved = {}
        self.quote_age = 0
        self.bid = 100
        self.result_status = "new"

    def call(self, method, path, **kwargs):
        if method == "DELETE":
            self.deleted.append(path)
            return None
        if path == "/v2/clock":
            return self.clock
        if path == "/v2/account":
            return self.account
        if path == "/v2/positions":
            return self.positions
        if path.endswith("/quotes/latest"):
            return {"quote": {"ap": 100, "bp": self.bid,
                             "t": (datetime.now(timezone.utc)-timedelta(seconds=self.quote_age)).isoformat()}}
        raise AssertionError(path)

    def orders(self):
        return self.open

    def submit_once(self, payload):
        cid = payload["client_order_id"]
        if cid not in self.saved:
            self.submitted.append(payload)
            self.saved[cid] = {**payload, "id": cid, "status": self.result_status}
        return self.saved[cid]


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "STATE", tmp_path/"state.json")
    monkeypatch.setattr(engine, "STATUS", tmp_path/"status.json")
    configs = [yaml.safe_load(open(p)) for p in ("config_high.yaml", "config_low.yaml")]
    api = API()
    state = {"day": market_day(datetime.now(timezone.utc)), "attempted": []}
    signals = {"TQQQ": {"signal": "buy", "atr": 2, "at": time.time()}}
    return engine.Engine(api, configs, signals, state), api


@pytest.mark.parametrize("equity,blocked,exiting", [
    (99501, False, False), (99500, True, False), (99001, True, False),
    (99000, True, True), (98000, True, True)])
def test_daily_boundaries(setup, equity, blocked, exiting):
    e, api = setup
    api.account["equity"] = equity
    e.tick()
    assert bool(e.state.get("entry_blocked")) == blocked
    assert not api.submitted if blocked else bool(api.submitted)
    # Flat accounts finish liquidation immediately, still blocked all day.
    if exiting:
        assert e.state["entry_reason"] == "liquidation confirmed; no re-entry today"


def test_daily_cutoff_latches_after_recovery_and_restart(setup):
    e, api = setup
    api.account["equity"] = 99400
    e.tick()
    api.account["equity"] = 101000
    restored = engine.Engine(api, e.configs, e.signals, json.loads(engine.STATE.read_text()))
    restored.tick()
    assert restored.state["entry_blocked"]
    assert not api.submitted


def test_daily_rollover_resets_but_permanent_halt_does_not(setup):
    e, api = setup
    e.state.update(day="2000-01-01", entry_blocked=True, permanent_halt="account loss budget")
    e.tick()
    assert e.state["entry_blocked"] and not api.submitted


def test_previous_session_unfinished_exit_survives(setup):
    e, api = setup
    e.state.update(day="2000-01-01", liquidating="daily loss exit")
    api.positions = [position()]
    e.tick()
    assert api.submitted[0]["side"] == "sell"
    assert e.state["entry_blocked"]


def test_loss_exit_does_not_wait_for_signals(setup):
    e, api = setup
    e.signals.clear()
    api.account["equity"] = 98000
    api.positions = [position(), position("SPY")]
    status = e.tick()
    assert len(api.submitted) == 2
    assert all(p["side"] == "sell" for p in api.submitted)
    assert status["liquidating"] == "daily loss exit"
    assert status["open_positions"] == 2  # requested is NOT closed


def test_eod_uses_broker_close_and_exits_losing_holdings(setup):
    e, api = setup
    api.clock["next_close"] = (datetime.now(timezone.utc)+timedelta(minutes=4)).isoformat()
    api.positions = [position()]
    api.positions[0]["unrealized_pl"] = "-200"
    e.tick()
    assert api.submitted[0]["side"] == "sell"
    assert e.state["liquidating"] == "end of session"


def test_early_close_policy():
    state = {"day": "2026-11-27"}
    policy = dict(entry_loss_limit_pct=.005, daily_loss_limit_pct=.01,
                  starting_equity=100000, max_account_loss_pct=.1,
                  max_drawdown_pct=.1, close_buffer_seconds=300)
    apply_policy(state, {"equity": 100000, "last_equity": 100000},
                 {"timestamp": "2026-11-27T12:55:00-05:00",
                  "is_open": True, "next_close": "2026-11-27T13:00:00-05:00"}, [position()], policy)
    assert state["liquidating"] == "end of session"


def test_cancels_bracket_then_waits_for_confirmed_cancellation(setup):
    e, api = setup
    api.account["equity"] = 98000
    api.positions = [position()]
    api.open = [stop()]
    e.tick()
    assert api.deleted and not api.submitted
    e.tick()  # still in inventory, no duplicate sell
    assert not api.submitted
    api.open = []
    e.tick()
    assert len(api.submitted) == 1
    e.tick()  # stale position but same client ID reconciles existing exit
    assert len(api.submitted) == 1


def test_pending_partial_exit_not_duplicated(setup):
    e, api = setup
    api.account["equity"] = 98000
    api.positions = [position(qty="1")]
    api.open = [{"id": "exit1", "client_order_id": "safe-exit-abc", "symbol": "TQQQ",
                 "status": "partially_filled", "qty": "2", "filled_qty": "1", "side": "sell"}]
    e.tick()
    assert not api.submitted and not api.deleted


def test_rejected_exit_cooldown_then_new_id(setup):
    e, api = setup
    api.account["equity"] = 98000
    api.positions = [position()]
    api.result_status = "rejected"
    assert e.tick()["errors"]
    assert len(api.submitted) == 1
    e.tick()
    assert len(api.submitted) == 1
    e.state["exit_retries"]["TQQQ"]["after"] = 0
    api.result_status = "new"
    e.tick()
    assert len(api.submitted) == 2
    assert api.submitted[0]["client_order_id"] != api.submitted[1]["client_order_id"]


def test_unprotected_partial_bracket_cancels_entry_and_blocks_account(setup):
    e, api = setup
    api.positions = [position(qty="1")]
    api.open = [{"id": "parent", "symbol": "TQQQ", "side": "buy", "type": "limit",
                 "status": "partially_filled", "legs": [stop(qty="2", status="held")]}]
    e.tick()
    assert e.state["entry_blocked"] and e.state["liquidating"]
    assert api.deleted and not api.submitted


@pytest.mark.parametrize("order", [
    stop(qty="1"), stop(status="held"), stop(status="canceled"),
    stop(side="buy"), stop(type="stop_limit"), stop(filled_qty="1")])
def test_bad_stop_is_not_coverage(order):
    assert not stop_coverage(position(), [order])


def test_nested_stop_deduplicated():
    s = stop(qty="1")
    assert not stop_coverage(position(), [{"id": "p", "status": "filled", "legs": [s]}, s])
    assert stop_coverage(position(), [stop()])


def test_accepted_bracket_has_whole_qty_and_both_exit_legs(setup):
    e, api = setup
    e.tick()
    p = api.submitted[0]
    assert p["order_class"] == "bracket" and "notional" not in p
    assert int(p["qty"]) > 0 and p["time_in_force"] == "day"
    assert 0 < p["stop_loss"]["stop_price"] < p["limit_price"] < p["take_profit"]["limit_price"]
    e.tick()
    assert len(api.submitted) == 1  # no same-day re-entry, even if inventory lags


def test_cash_and_portfolio_caps(setup):
    e, api = setup
    c = e.configs[0]
    assert c["risk"]["capital_fraction"] == .25
    qty, limit = entry_budget(c, api.account, [dict(position(), market_value="24950")], 100, 2)
    assert qty == 0
    api.account["cash"] = "100"
    qty, limit = entry_budget(c, api.account, [], 100, 2)
    assert qty == 0


def test_pending_buy_prevents_other_entry(setup):
    e, api = setup
    api.open = [{"id": "x", "symbol": "SPY", "side": "buy", "status": "new"}]
    e.tick()
    assert not api.submitted


def test_stale_quote_blocks_entry(setup):
    e, api = setup
    api.quote_age = 120
    e.tick()
    assert not api.submitted


def test_stale_clock_fails_before_order_submission(setup):
    e, api = setup
    api.clock["timestamp"] = (datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
    with pytest.raises(RuntimeError, match="clock is stale"):
        e.tick()
    assert not api.submitted


def test_fresh_state_queues_inherited_exit_when_closed(setup):
    previous, api = setup
    api.clock["is_open"] = False
    api.positions = [position("SPY", "1.23456789")]
    e = engine.Engine(api, previous.configs, {}, None)
    e.tick()
    assert api.submitted[0]["qty"] == "1.234567890"
    assert api.submitted[0]["side"] == "sell"
    assert e.state["entry_blocked"]


def test_strategy_exit_works_while_buys_blocked(setup):
    e, api = setup
    e.state["entry_blocked"] = True
    e.signals["TQQQ"]["signal"] = "sell"
    api.positions = [position()]
    api.open = [stop()]
    e.tick()
    assert api.deleted
    assert e.state["exit_intents"]["TQQQ"] == "strategy exit"


def test_trailing_exit_is_retained_after_signal_change(setup):
    e, api = setup
    api.positions = [position()]
    api.open = [stop()]
    api.bid = 110
    e.tick()
    assert e.state["trailing_stops"]["TQQQ"] == 108
    api.bid = 107
    e.tick()
    assert e.state["exit_intents"]["TQQQ"] == "trailing exit"
    api.open = []
    e.signals.clear()
    e.tick()
    assert api.submitted[-1]["side"] == "sell"


def test_live_configuration_refused(setup):
    e, api = setup
    configs = deepcopy(e.configs)
    configs[0]["mode"] = "alpaca_live"
    with pytest.raises(ValueError, match="PAPER"):
        engine.Engine(api, configs, {})


def test_transport_never_uses_live_endpoint(monkeypatch):
    class Session:
        headers = {}
        def request(self, method, url, **kwargs):
            assert url.startswith("https://paper-api.alpaca.markets/")
            return type("Response", (), {"ok": True, "status_code": 200,
                                         "content": b"{}", "json": lambda _: {}})()
    monkeypatch.setattr(engine.requests, "Session", Session)
    engine.PaperAPI("test", "test").call("GET", "/v2/account")


def test_submit_once_reconciles_before_retry(monkeypatch):
    api = engine.PaperAPI("test", "test")
    methods = []
    def call(method, path, **kwargs):
        methods.append(method)
        return {"id": "existing"}
    monkeypatch.setattr(api, "call", call)
    assert api.submit_once({"client_order_id": "unique"})["id"] == "existing"
    assert methods == ["GET"]
