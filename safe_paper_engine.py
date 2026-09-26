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
from datetime import datetime, timezone

import requests
import yaml
from dotenv import load_dotenv
from paper_safety import (NY, TERMINAL, timestamp, market_day, active_orders,
                          stop_coverage, quantity, apply_policy, entry_budget)

STATE = Path(os.getenv("AUTOTRADER_STATE_DIR", os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "."))) / "safety_state.json"
STATUS = Path("safety_status.json")


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
            raise RuntimeError(f"Paper API {method} {path}: HTTP {response.status_code}")
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
        if sum(c["risk"]["capital_fraction"] for c in configs) > 1:
            raise ValueError("Portfolio allocation exceeds account cash")
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

    def persist(self):
        save(STATE, self.state)

    def cancel(self, order):
        self.api.call("DELETE", f"/v2/orders/{order['id']}")

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
        order = self.api.submit_once(payload)
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
        clock = self.api.call("GET", "/v2/clock")
        clock_age = (datetime.now(timezone.utc)-timestamp(clock["timestamp"])).total_seconds()
        if not -5 <= clock_age <= 30:
            raise RuntimeError("Broker clock is stale")
        account = self.api.call("GET", "/v2/account")
        positions = self.api.call("GET", "/v2/positions")
        orders = self.api.orders()
        daily = apply_policy(self.state, account, clock, positions, self.policy)
        held = {p["symbol"] for p in positions}
        for symbol in list(self.state.setdefault("exit_intents", {})):
            if symbol not in held and not active_orders(orders, symbol):
                del self.state["exit_intents"][symbol]
        for symbol in list(self.state.setdefault("trailing_highs", {})):
            if symbol not in held:
                del self.state["trailing_highs"][symbol]
                self.state.setdefault("trailing_stops", {}).pop(symbol, None)
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
            if signal and time.time()-signal["at"] < 180 and p["symbol"] in self.owner:
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
                    if bid <= stop:
                        self.status["actions"][p["symbol"]] = self.exit_position(p, orders, "trailing exit")
                        return self.publish()

        if self.state.get("entry_blocked"):
            # Cancel unfilled entries too, not just prevent new submissions.
            for o in active_orders(orders):
                if o.get("side") == "buy":
                    self.cancel(o)
            return self.publish()
        if not clock["is_open"] or active_orders(orders) and any(
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
            quote = self.api.call("GET", f"/v2/stocks/{symbol}/quotes/latest",
                                  params={"feed": "iex"}, market_data=True)["quote"]
            age = (datetime.now(timezone.utc)-timestamp(quote["t"])).total_seconds()
            if not 0 <= age <= 30 or float(quote.get("ap") or 0) <= 0:
                continue
            ask, atr_value = float(quote["ap"]), signal["atr"]
            qty, limit = entry_budget(config, account, positions, ask, atr_value)
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
            self.persist()
            try:
                placed = self.api.submit_once(payload)
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
        self.status["entry_blocked"] = self.state.get("entry_blocked", False)
        self.status["reason"] = self.state.get("entry_reason", "")
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
    configs = [yaml.safe_load(Path(p).read_text()) for p in ("config_high.yaml", "config_low.yaml")]
    key, secret = os.environ["ALPACA_API_KEY"], os.environ["ALPACA_API_SECRET"]
    signals = {}
    def collect():
        from price_feed import AlpacaPriceFeed
        from strategy import build_strategy, atr
        feed = AlpacaPriceFeed(key, secret)
        while True:
            for config in configs:
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
            # Stop new exposure on incomplete/uncertain broker reads.
            engine.state["entry_blocked"] = True
            engine.state["entry_reason"] = "safety API failure; entries locked for this session"
            engine.persist()
            engine.status.update({"updated_at": datetime.now(timezone.utc).isoformat(),
                                  "errors": [str(exc)], "mode": "paper"})
            engine.publish()
            print(f"[safety] {exc}", flush=True)
        time.sleep(max(1, 10-(time.monotonic()-started)))


if __name__ == "__main__":
    main()
