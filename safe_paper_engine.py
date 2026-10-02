"""Single paper-only order writer with independent signal collection.

The execution/safety loop never waits for a strategy's historical bars.
Missing/corrupt local state blocks entries for the current NY date and queues
inherited holdings for exit. Accepted orders are not reported as filled.
"""
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import queue
import math
from datetime import datetime, timezone

import requests
import yaml
from dotenv import load_dotenv
from paper_safety import (NY, TERMINAL, timestamp, market_day, active_orders,
                          stop_coverage, quantity, apply_policy, entry_budget)

STATE = Path(os.getenv("AUTOTRADER_STATE_DIR", os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "."))) / "safety_state.json"
STATUS = Path("safety_status.json")
PROTECTION_RECOVERY_SECONDS = 30


class APIError(RuntimeError):
    def __init__(self, method, path, status):
        super().__init__(f"Paper API {method} {path}: HTTP {status}")
        self.method, self.status = method, status


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(path)


class PaperAPI:
    def __init__(self, key, secret):
        self.session = requests.Session()
        self.session.headers.update({"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})

    def call(self, method, path, data=None, params=None, missing_ok=False, market_data=False):
        # No live endpoint, even if a live-confirmation environment variable exists.
        base = "https://data.alpaca.markets" if market_data else "https://paper-api.alpaca.markets"
        response = self.session.request(method, base+path, json=data, params=params, timeout=5)
        if response.status_code == 404 and missing_ok:
            return None
        if not response.ok:
            raise APIError(method, path, response.status_code)
        return response.json() if response.content else None

    def orders(self):
        orders = self.call("GET", "/v2/orders",
                           params={"status": "open", "nested": "true", "limit": 500})
        if len(orders) >= 500:
            raise RuntimeError("Open-order inventory may be truncated; entries disabled")
        return orders

    def submit_once(self, payload):
        # Retrying after a network timeout uses the SAME client id.
        existing = self.call("GET", "/v2/orders:by_client_order_id",
                             params={"client_order_id": payload["client_order_id"]},
                             missing_ok=True)
        return existing or self.call("POST", "/v2/orders", data=payload)


def identity(prefix, day, symbol, extra=""):
    digest = hashlib.sha256(f"{day}|{symbol}|{extra}".encode()).hexdigest()[:24]
    return f"safe-{prefix}-{digest}"


class Engine:
    def __init__(self, api, configs, signals, state=None):
        if any(c.get("mode") != "alpaca_paper" or c.get("market") != "stock" for c in configs):
            raise ValueError("Safety engine only accepts Alpaca PAPER stock configurations")
        fractions=[float(c["risk"]["capital_fraction"]) for c in configs]
        if any(not math.isfinite(v) or v<0 for v in fractions) or sum(fractions) > .80000001:
            raise ValueError("Paper allocations must preserve at least 20% reserve")
        self.api, self.configs, self.signals = api, configs, signals
        self.owner = {s: c for c in configs for s in c["stock"]["symbols"]}
        if len(self.owner) != sum(len(c["stock"]["symbols"]) for c in configs):
            raise ValueError("Portfolio symbols must be disjoint")
        self.policy = {
            "entry_loss_limit_pct": .005, "daily_loss_limit_pct": .01,
            "close_buffer_seconds": 300, "starting_equity": 100000,
            "max_account_loss_pct": .10, "max_drawdown_pct": .10,
        }
        for c in configs:
            if (c["risk"].get("entry_loss_limit_pct") != .005 or
                    c["risk"]["daily_loss_limit_pct"] != .01 or
                    not c["day_trading"]["close_at_eod"]):
                raise ValueError("Configuration disagrees with approved safety policy")
        self.state = state if state is not None else {
            "day": market_day(datetime.now(timezone.utc)), "entry_blocked": True,
            "entry_reason": "fresh safety state: no new entries today",
            "bootstrap": True, "attempted": [],
        }
        self.status = {}
        self.events = queue.Queue(maxsize=100)
        self.previous_event = None
        self.operation_stage = "inventory"
        self.experiment_health = {}

    def category_budgets(self, account, positions):
        day=self.state["day"]
        book=self.state.get("daily_purchase_budget")
        if not book or book.get("day") != day:
            # Existing attempts without the new ledger cannot be reconstructed
            # safely. Migration waits for the next session instead of resetting
            # any existing intraday purchase/loss allowance.
            if self.state.get("attempted") and not self.state.get("entry_blocked"):
                self.state["entry_blocked"]=True
                self.state["entry_reason"]="daily budget migration: wait for next session"
            baseline=float(account["last_equity"])
            legacy={c["name"]:baseline*c["risk"]["capital_fraction"] for c in self.configs
                    if any(s in c["stock"]["symbols"] for s in self.state.get("attempted",[]))}
            book=dict(day=day,baseline=baseline,committed=legacy,legacy_allowance_held=bool(legacy))
            self.state["daily_purchase_budget"]=book
        base=min(book["baseline"],float(account["equity"]))
        result={}
        for c in self.configs:
            cap=base*c["risk"]["capital_fraction"]
            committed=float(book["committed"].get(c["name"],0))
            exposure=sum(abs(float(p["market_value"])) for p in positions if p["symbol"] in c["stock"]["symbols"])
            result[c["name"]]=dict(fraction=c["risk"]["capital_fraction"],
                daily_cap=round(cap,2),committed=round(committed,2),
                remaining=max(0,cap-committed),exposure=round(exposure,2))
        return result

    def persist(self):
        save(STATE, self.state)

    def cancel(self, order):
        self.operation_stage = "write"
        self.api.call("DELETE", f"/v2/orders/{order['id']}")

    def submit(self, payload):
        self.operation_stage = "write"
        return self.api.submit_once(payload)

    def handle_failure(self, exc):
        transient = (isinstance(exc, requests.exceptions.RequestException)
                     or isinstance(exc, APIError) and (exc.status == 429 or exc.status >= 500))
        if transient and self.operation_stage == "inventory":
            self.state["connection_pause"] = True
            self.state["recovery_checks"] = 0
            self.state["connection_error"] = str(exc)
        else:
            # An uncertain write must be reconciled; a read outage is separate
            # from a latched daily loss cutoff.
            self.state["entry_blocked"] = True
            self.state["entry_reason"] = "broker operation failed or uncertain; entries locked for this session"
        self.persist()
        self.status.update({"updated_at": datetime.now(timezone.utc).isoformat(),
                            "errors": [str(exc)], "mode": "paper",
                            "verified_stops": None, "open_positions": None})
        return self.publish()

    def repair_partial(self, position, orders):
        """Cancel the remainder, then cover the actual fill with a standalone stop.

        Return True only for a recognized entry undergoing bounded repair.
        Unknown holdings still take the original emergency exit path.
        """
        symbol = position["symbol"]
        repairs = self.state.setdefault("protection_repairs", {})
        repair = repairs.get(symbol)
        if repair is None:
            expected = identity("entry", self.state["day"], symbol)
            parent = next((o for o in orders if o.get("symbol") == symbol
                           and o.get("client_order_id") == expected
                           and o.get("order_class") == "bracket"
                           and o.get("side") == "buy"
                           and o.get("status") == "partially_filled"
                           and 0 < float(o.get("filled_qty") or 0) < float(o.get("qty") or 0)), None)
            if parent is None:
                return False
            legs = parent.get("legs") or []
            stop_leg = next((o for o in legs if o.get("side") == "sell"
                             and o.get("type") == "stop"), {})
            take_leg = next((o for o in legs if o.get("side") == "sell"
                             and o.get("type") == "limit"), {})
            stop_price = float(stop_leg.get("stop_price") or 0)
            take_price = float(take_leg.get("limit_price") or 0)
            if not 0 < stop_price < take_price or float(position["qty"]) <= 0:
                return False
            repair = {"started_at": time.time(), "stop_price": stop_price,
                      "take_price": take_price, "entry_id": expected}
            repairs[symbol] = repair
            self.persist()
        if time.time()-repair["started_at"] >= PROTECTION_RECOVERY_SECONDS:
            self.status["errors"].append(f"{symbol}: protection repair exceeded 30 seconds")
            return False
        pending = active_orders(orders, symbol)
        own_stop = next((o for o in pending if o.get("client_order_id", "").startswith("safe-protect-")), None)
        if own_stop:
            self.status["actions"][symbol] = "filled shares awaiting broker stop verification"
            return True
        if pending:
            # Cancel roots once. Canceling a bracket root also cancels its legs.
            for root in orders:
                if root.get("symbol") == symbol:
                    self.cancel(root)
            orders = self.api.orders()
            if active_orders(orders, symbol):
                self.status["actions"][symbol] = "partial fill: canceling unfilled remainder before protection"
                return True
        # Cancellation may race with another fill; re-read the actual position.
        actual = next((p for p in self.api.call("GET", "/v2/positions")
                       if p["symbol"] == symbol), None)
        if actual is None:
            repairs.pop(symbol, None)
            self.persist()
            self.status["actions"][symbol] = "partial-fill position already closed; reconciling inventory"
            return True
        quote = self.api.call("GET", f"/v2/stocks/{symbol}/quotes/latest",
                              params={"feed": "iex"}, market_data=True)["quote"]
        age = (datetime.now(timezone.utc)-timestamp(quote["t"])).total_seconds()
        if not 0 <= age <= 30 or float(actual["qty"]) <= 0:
            return False
        if float(quote.get("bp") or 0) <= repair["stop_price"]:
            return False  # price has already crossed the intended stop: exit
        if time.time()-repair["started_at"] >= PROTECTION_RECOVERY_SECONDS:
            return False
        payload = {"symbol": symbol, "side": "sell", "type": "stop",
                   "qty": quantity(actual["qty"]), "stop_price": repair["stop_price"],
                   "time_in_force": "day",
                   "client_order_id": identity("protect", self.state["day"], symbol,
                                              repair["entry_id"]+"|"+quantity(actual["qty"]))}
        placed = self.submit(payload)
        if placed.get("status") in TERMINAL:
            return False
        self.state.setdefault("partial_take_prices", {})[symbol] = repair["take_price"]
        self.persist()
        refreshed = self.api.orders()
        if stop_coverage(actual, refreshed):
            repairs.pop(symbol, None)
            self.persist()
            self.status["actions"][symbol] = "partial fill retained; actual filled quantity protected at broker"
        else:
            self.status["actions"][symbol] = "stop submitted for filled shares; verification pending"
        return True

    def exit_position(self, position, orders, reason):
        symbol = position["symbol"]
        self.state.setdefault("exit_intents", {})[symbol] = reason
        self.persist()
        pending = active_orders(orders, symbol)
        # Keep an already-submitted liquidation; do not cancel and duplicate it.
        if any(o.get("client_order_id", "").startswith("safe-exit-") for o in pending):
            return "exit pending"
        if pending:
            # Cancellation of a bracket member can cancel the group. Confirm
            # no orders remain on a later cycle before sending the market exit.
            errors = []
            for order in pending:
                try:
                    self.cancel(order)
                except Exception as exc:
                    errors.append(str(exc))
            if errors:
                self.status["errors"].extend(errors)
            return "canceling conflicting orders before exit"
        self.state.setdefault("attempted", [])
        if symbol not in self.state["attempted"]:
            self.state["attempted"].append(symbol)  # no same-day re-entry
        self.persist()
        qty = quantity(position["qty"])
        retries = self.state.setdefault("exit_retries", {}).get(symbol, {})
        if time.time() < retries.get("after", 0):
            return "exit rejected/canceled; retry scheduled after 60 seconds"
        payload = {"symbol": symbol, "qty": qty, "type": "market",
                   "side": "sell" if float(position["qty"]) > 0 else "buy",
                   "time_in_force": "day",
                   "client_order_id": identity("exit", self.state["day"], symbol,
                                              f"{qty}|{retries.get('generation', 0)}")}
        order = self.submit(payload)
        if order.get("status") in {"rejected", "canceled", "expired"}:
            # A confirmed terminal order cannot fill again. A fresh inventory
            # and a 60-second cooldown precede the next uniquely identified exit.
            self.state["exit_retries"][symbol] = {
                "generation": retries.get("generation", 0)+1, "after": time.time()+60}
            self.persist()
            raise RuntimeError(f"{symbol}: exit {order['status']}; review required")
        if order.get("status") == "filled":
            return "exit filled at broker; awaiting position reconciliation"
        return f"exit requested: {reason}"

    def tick(self):
        self.operation_stage = "inventory"
        clock = self.api.call("GET", "/v2/clock")
        clock_age = (datetime.now(timezone.utc)-timestamp(clock["timestamp"])).total_seconds()
        if not -5 <= clock_age <= 30:
            raise RuntimeError("Broker clock is stale")
        account = self.api.call("GET", "/v2/account")
        positions = self.api.call("GET", "/v2/positions")
        orders = self.api.orders()
        daily = apply_policy(self.state, account, clock, positions, self.policy)
        budgets=self.category_budgets(account,positions)
        if self.state.get("connection_pause"):
            self.state["recovery_checks"] = self.state.get("recovery_checks", 0)+1
            if self.state["recovery_checks"] >= 2:
                self.state.pop("connection_pause", None)
                self.state.pop("connection_error", None)
                self.state.pop("recovery_checks", None)
        held = {p["symbol"] for p in positions}
        for symbol in list(self.state.setdefault("exit_intents", {})):
            if symbol not in held and not active_orders(orders, symbol):
                del self.state["exit_intents"][symbol]
        for symbol in list(self.state.setdefault("trailing_highs", {})):
            if symbol not in held:
                del self.state["trailing_highs"][symbol]
                self.state.setdefault("trailing_stops", {}).pop(symbol, None)
        for symbol in list(self.state.setdefault("protection_repairs", {})):
            p = next((p for p in positions if p["symbol"] == symbol), None)
            if ((p is not None and stop_coverage(p, orders))
                    or (p is None and not active_orders(orders, symbol))):
                if p is not None:
                    # A stop POST may have timed out after broker acceptance.
                    # Preserve the exit plan when its coverage is reconciled.
                    self.state.setdefault("partial_take_prices", {})[symbol] = (
                        self.state["protection_repairs"][symbol]["take_price"])
                del self.state["protection_repairs"][symbol]
        for symbol in list(self.state.setdefault("partial_take_prices", {})):
            if symbol not in held and not active_orders(orders, symbol):
                del self.state["partial_take_prices"][symbol]
        self.persist()  # latch the cutoff BEFORE sending any order
        self.status = {
            "updated_at": datetime.now(timezone.utc).isoformat(), "mode": "paper",
            "policy": self.policy, "entry_blocked": self.state.get("entry_blocked", False),
            "reason": self.state.get("entry_reason", ""),
            "liquidating": self.state.get("liquidating"),
            "daily_pnl_pct": round(daily*100, 3), "market_open": clock["is_open"],
            "open_positions": len(positions), "actions": {}, "errors": [],
            "verified_stops": sum(stop_coverage(p, orders) for p in positions),
            "baseline_equity": float(account["last_equity"]),
            "peak_equity": self.state["peak_equity"],
            "allocations": {c["name"]: c["risk"]["capital_fraction"] for c in self.configs},
            "signals": {s: {"signal": v["signal"], "age_seconds": round(time.time()-v["at"])}
                        for s, v in list(self.signals.items())},
            "state_persistent": bool(os.getenv("RAILWAY_VOLUME_MOUNT_PATH") or
                                     os.getenv("AUTOTRADER_STATE_DIR")),
            "controller_version": "2026-10-02-paper-budgets",
            "category_budgets": budgets,
            "reserve_fraction": round(1-sum(c["risk"]["capital_fraction"] for c in self.configs),4),
            "experiment": dict(self.experiment_health),
        }
        if self.state.get("liquidating"):
            # Global exit is independent of signals, profitability and open/closed
            # market status. Closed-session orders queue for the next eligible open.
            for order in active_orders(orders):
                if order.get("side") == "buy" and not order.get("client_order_id", "").startswith("safe-exit-"):
                    try:
                        self.cancel(order)
                    except Exception as exc:
                        self.status["errors"].append(str(exc))
            for p in positions:
                try:
                    self.status["actions"][p["symbol"]] = self.exit_position(p, orders, self.state["liquidating"])
                except Exception as exc:
                    self.status["errors"].append(str(exc))
            if not positions and not active_orders(orders):
                self.state.pop("liquidating", None)
                self.state["entry_blocked"] = True
                self.state["entry_reason"] = "liquidation confirmed; no re-entry today"
                self.persist()
            return self.publish()

        # If an inherited/external position has no verified broker protection,
        # flatten it rather than silently trading with a software-only stop.
        unprotected = [p for p in positions if not stop_coverage(p, orders)]
        if unprotected:
            fatal = []
            for p in unprotected:
                if not self.repair_partial(p, orders):
                    fatal.append(p)
            if not fatal:
                # No other exposure is allowed during protection transitions.
                return self.publish()
            self.state["entry_blocked"] = True
            self.state["entry_reason"] = "broker protection missing or unverified"
            self.state["liquidating"] = self.state["entry_reason"]
            self.persist()
            for order in active_orders(orders):
                if order.get("side") == "buy" and not order.get("client_order_id", "").startswith("safe-exit-"):
                    try:
                        self.cancel(order)
                    except Exception as exc:
                        self.status["errors"].append(str(exc))
            for p in unprotected:
                try:
                    self.status["actions"][p["symbol"]] = self.exit_position(p, orders, self.state["entry_reason"])
                except Exception as exc:
                    self.status["errors"].append(str(exc))
            return self.publish()

        # Experiment entries are valid only during the opening window. A DAY
        # order must not linger and unexpectedly open an afternoon position.
        for order in orders:
            config=self.owner.get(order.get("symbol"))
            if (config and config["strategy"]["name"]=="active_opening_range_paper"
                    and order.get("side")=="buy" and order.get("status") not in TERMINAL):
                local_clock=timestamp(clock["timestamp"]).astimezone(NY)
                submitted=order.get("submitted_at") or order.get("created_at")
                expired=(local_clock.hour>=11 or submitted and
                         (timestamp(clock["timestamp"])-timestamp(submitted)).total_seconds()>60)
                if expired:
                    self.cancel(order)
                    self.status["actions"][order["symbol"]]="experiment entry expired: cancellation requested"
                    return self.publish()

        # Protective and strategy exits still run while purchases are blocked.
        for p in positions:
            signal = self.signals.get(p["symbol"])
            intent = self.state["exit_intents"].get(p["symbol"])
            if intent:
                self.status["actions"][p["symbol"]] = self.exit_position(p, orders, intent)
                return self.publish()
            if signal and signal.get("signal") == "sell" and time.time()-signal["at"] < 180:
                self.status["actions"][p["symbol"]] = self.exit_position(p, orders, "strategy exit")
                return self.publish()
            # Preserve the existing break-even/trailing exit plan, using a
            # fresh bid rather than yesterday's daily close. Static broker
            # stops stay in force until an exit is actually requested.
            if (signal and time.time()-signal["at"] < 180 and p["symbol"] in self.owner
                    and self.owner[p["symbol"]]["strategy"]["name"] != "active_opening_range_paper"):
                quote = self.api.call("GET", f"/v2/stocks/{p['symbol']}/quotes/latest",
                                      params={"feed": "iex"}, market_data=True)["quote"]
                age = (datetime.now(timezone.utc)-timestamp(quote["t"])).total_seconds()
                bid = float(quote.get("bp") or 0)
                if clock["is_open"] and 0 <= age <= 30 and bid > 0:
                    from risk import RiskManager, RiskConfig
                    risk = self.owner[p["symbol"]]["risk"]
                    manager = RiskManager(RiskConfig(**{
                        k: v for k, v in risk.items() if k in RiskConfig.__dataclass_fields__}))
                    high = max(bid, self.state["trailing_highs"].get(p["symbol"], bid))
                    self.state["trailing_highs"][p["symbol"]] = high
                    entry = float(p["avg_entry_price"])
                    previous_stop = self.state.setdefault("trailing_stops", {}).get(
                        p["symbol"], entry-signal["atr"]*risk["atr_stop_mult"])
                    stop = manager.trailing_stop(entry, high, signal["atr"], previous_stop)
                    self.state["trailing_stops"][p["symbol"]] = stop
                    self.persist()
                    take = self.state.get("partial_take_prices", {}).get(p["symbol"])
                    if bid <= stop or (take and bid >= take):
                        reason = "take-profit exit" if take and bid >= take else "trailing exit"
                        self.status["actions"][p["symbol"]] = self.exit_position(p, orders, reason)
                        return self.publish()

        if self.state.get("entry_blocked"):
            # Cancel unfilled entries too, not just prevent new submissions.
            for o in active_orders(orders):
                if o.get("side") == "buy":
                    self.cancel(o)
            return self.publish()
        if not clock["is_open"]:
            for order in active_orders(orders):
                if order.get("side") == "buy":
                    self.cancel(order)
            return self.publish()
        if self.state.get("connection_pause"):
            return self.publish()
        if active_orders(orders) and any(
                o.get("side") == "buy" for o in active_orders(orders)):
            return self.publish()
        if account.get("trading_blocked") or account.get("account_blocked"):
            raise RuntimeError("Broker account blocks trading")
        for symbol, config in self.owner.items():
            if (any(p["symbol"] == symbol for p in positions)
                    or active_orders(orders, symbol)
                    or symbol in self.state.get("attempted", [])):
                continue
            signal = self.signals.get(symbol)
            if not signal or time.time()-signal["at"] > 180 or signal["signal"] != "buy":
                continue
            experimental=config["strategy"]["name"] == "active_opening_range_paper"
            if experimental and sum(s in config["stock"]["symbols"] for s in self.state.get("attempted",[]))>=5:
                continue
            if experimental and (signal.get("market_day")!=self.state["day"] or
                    timestamp(clock["timestamp"])>=timestamp(signal["deadline"])):
                continue
            quote = self.api.call("GET", f"/v2/stocks/{symbol}/quotes/latest",
                                  params={"feed": "iex"}, market_data=True)["quote"]
            age = (datetime.now(timezone.utc)-timestamp(quote["t"])).total_seconds()
            if not 0 <= age <= 30 or float(quote.get("ap") or 0) <= 0:
                continue
            ask, atr_value = float(quote["ap"]), signal["atr"]
            if experimental:
                atr_value=ask-float(signal["stop_price"])
            qty, limit = entry_budget(config, account, positions, ask, atr_value)
            if experimental and limit>float(signal["limit_cap"]):
                continue
            category=budgets[config["name"]]
            total_cap=min(float(account["equity"]),float(account["last_equity"]))*sum(c["risk"]["capital_fraction"] for c in self.configs)
            total_used=sum(abs(float(p["market_value"])) for p in positions)
            qty=min(qty,int(max(0,min(category["remaining"],total_cap-total_used))/limit)) if limit>0 else 0
            if qty < 1:
                continue
            stop = round(ask-atr_value*config["risk"]["atr_stop_mult"], 2)
            take = round(ask+atr_value*config["risk"]["atr_take_mult"], 2)
            if not 0 < stop < limit < take:
                continue
            payload = {"symbol": symbol, "qty": str(qty), "side": "buy",
                       "type": "limit", "limit_price": limit, "time_in_force": "day",
                       "order_class": "bracket", "stop_loss": {"stop_price": stop},
                       "take_profit": {"limit_price": take},
                       "client_order_id": identity("entry", self.state["day"], symbol)}
            self.state.setdefault("attempted", []).append(symbol)
            # Reserve BEFORE submission and persist even after cancellations or
            # uncertain responses. Sells never refill the daily purchase budget.
            ledger=self.state["daily_purchase_budget"]["committed"]
            ledger[config["name"]]=ledger.get(config["name"],0)+qty*limit
            self.persist()
            try:
                placed = self.submit(payload)
                if placed.get("order_class") != "bracket" or placed.get("status") in {"rejected", "canceled", "expired"}:
                    raise RuntimeError(f"{symbol}: protective bracket was not accepted")
                self.status["actions"][symbol] = "bracket entry submitted; fills and active stops awaiting verification"
            except Exception:
                self.state["entry_blocked"] = True
                self.state["entry_reason"] = "entry submission failed or uncertain; review required"
                self.persist()
                raise
            break  # re-read risk, positions and protection before any next entry
        return self.publish()

    def publish(self):
        paused = self.state.get("connection_pause", False)
        repairing = bool(self.state.get("protection_repairs"))
        self.status["connection_paused"] = paused
        self.status["protection_repairing"] = repairing
        self.status["entry_blocked"] = bool(self.state.get("entry_blocked", False) or paused or repairing)
        self.status["reason"] = self.state.get("entry_reason", "") or (
            "connection recovery: waiting for two complete broker checks" if paused else
            "partial fill: protecting actual filled shares" if repairing else "")
        self.status["liquidating"] = self.state.get("liquidating")
        save(STATUS, self.status)
        event = json.dumps({k: self.status.get(k) for k in
                            ("entry_blocked", "reason", "liquidating", "open_positions", "errors", "actions")}, sort_keys=True)
        if event != self.previous_event:
            print("[paper-safety] " + event, flush=True)
            try:
                self.events.put_nowait(event)
            except queue.Full:
                pass  # notification outages never block risk checks
            self.previous_event = event
        return self.status


def main():
    load_dotenv()
    configs = [yaml.safe_load(Path(p).read_text()) for p in ("config_high.yaml", "config_low.yaml", "config_experiment.yaml")]
    key, secret = os.environ["ALPACA_API_KEY"], os.environ["ALPACA_API_SECRET"]
    signals = {}
    def collect():
        from price_feed import AlpacaPriceFeed
        from strategy import build_strategy, atr
        feed = AlpacaPriceFeed(key, secret)
        while True:
            for config in configs:
                if config["strategy"]["name"] == "active_opening_range_paper":
                    continue
                strategy = build_strategy(config["strategy"])
                for symbol in config["stock"]["symbols"]:
                    try:
                        bars = feed.fetch_ohlcv(symbol, config["stock"]["timeframe"], config["data"]["fetch_limit"])
                        if bars:
                            signals[symbol] = {"signal": strategy.evaluate(bars).value,
                                               "atr": atr(bars, 14)[-1], "at": time.time()}
                    except Exception:
                        signals.pop(symbol, None)  # no fresh evidence means no entry
            time.sleep(60)
    try:
        state = json.loads(STATE.read_text())
        if not isinstance(state, dict) or not state.get("day"):
            raise ValueError("Invalid safety state")
    except (OSError, ValueError):
        state = None
    api = PaperAPI(key, secret)
    engine = Engine(api, configs, signals, state)
    from active_paper_signals import collect as collect_experiment
    threading.Thread(target=collect_experiment,args=(PaperAPI(key,secret),configs[-1],signals,
        engine.experiment_health,key,secret),daemon=True).start()
    if state is None:
        # Seed the preserved drawdown guard from available broker history.
        # Thereafter the volume retains every observed intraday equity high.
        try:
            history = api.call("GET", "/v2/account/portfolio/history",
                               params={"period": "1M", "timeframe": "1D"})
            equities = [float(v) for v in history.get("equity", []) if v and float(v) > 0]
            if equities:
                engine.state["peak_equity"] = max(equities)
                engine.persist()
        except Exception:
            engine.state["permanent_halt"] = "initial drawdown baseline unavailable; review required"
            engine.persist()
    def notify():
        from alerts import AlertManager
        alerts = AlertManager()
        while True:
            alerts.send("AutoTrader PAPER safety\n" + engine.events.get())
    threading.Thread(target=notify, daemon=True).start()
    threading.Thread(target=collect, daemon=True).start()
    while True:
        started = time.monotonic()
        try:
            engine.tick()
        except Exception as exc:
            engine.handle_failure(exc)
            print(f"[safety] {exc}", flush=True)
        time.sleep(max(1, 10-(time.monotonic()-started)))


if __name__ == "__main__":
    main()
