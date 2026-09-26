"""Pure decisions for the approved paper-only account safety policy."""
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from math import isfinite
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
TERMINAL = {"filled", "canceled", "expired", "rejected", "replaced"}


def timestamp(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def market_day(now):
    return now.astimezone(NY).date().isoformat()


def flatten(orders):
    result = {}
    for order in orders:
        result[order["id"]] = order
        for leg in flatten(order.get("legs") or []):
            result[leg["id"]] = leg
    return list(result.values())


def active_orders(orders, symbol=None):
    return [o for o in flatten(orders) if o.get("status") not in TERMINAL
            and (symbol is None or o.get("symbol") == symbol)]


def stop_coverage(position, orders):
    """Held legs, buy stops, stop-limits and undersized stops are not coverage."""
    required = abs(float(position["qty"]))
    if float(position["qty"]) <= 0:
        return False
    covered = 0.0
    for o in active_orders(orders, position["symbol"]):
        if (o.get("side") == "sell" and o.get("type") == "stop"
                and o.get("status") in {"new", "accepted", "partially_filled"}
                and float(o.get("stop_price") or 0) > 0):
            covered += max(0, float(o.get("qty") or 0)-float(o.get("filled_qty") or 0))
    return required > 0 and covered + 1e-8 >= required


def quantity(value):
    return str(Decimal(str(abs(float(value)))).quantize(Decimal("0.000000001"),
                                                      rounding=ROUND_DOWN))


def apply_policy(state, account, clock, positions, policy):
    now = timestamp(clock["timestamp"])
    day = market_day(now)
    equity, baseline = float(account["equity"]), float(account["last_equity"])
    if not all(isfinite(v) and v > 0 for v in (equity, baseline)):
        raise ValueError("Account equity or previous close is unavailable")
    if state.get("day") != day:
        state["day"] = day
        state["entry_blocked"] = False
        state["entry_reason"] = ""
        state["attempted"] = []
        # An unfinished liquidation must survive midnight and a restart.
    state["peak_equity"] = max(float(state.get("peak_equity") or equity), equity)
    daily = equity / baseline - 1
    if equity <= baseline * (1-policy["entry_loss_limit_pct"]):
        state["entry_blocked"] = True
        state["entry_reason"] = "daily entry cutoff"
    reason = None
    if equity <= baseline * (1-policy["daily_loss_limit_pct"]):
        reason = "daily loss exit"
    if equity <= policy["starting_equity"] * (1-policy["max_account_loss_pct"]):
        reason = "account loss budget"
        state["permanent_halt"] = reason
    if equity <= state["peak_equity"] * (1-policy["max_drawdown_pct"]):
        reason = "maximum drawdown"
        state["permanent_halt"] = reason
    if state.get("permanent_halt"):
        reason = state["permanent_halt"]
    if clock["is_open"]:
        remaining = (timestamp(clock["next_close"])-now).total_seconds()
        if remaining <= policy["close_buffer_seconds"]:
            reason = reason or "end of session"
    if state.get("bootstrap") and positions:
        reason = reason or "inherited holdings: remove overnight exposure"
    held_days = state.setdefault("held_days", {})
    for p in positions:
        if p["symbol"] in held_days and held_days[p["symbol"]] != day:
            reason = reason or "overnight carryover"
        held_days.setdefault(p["symbol"], day)
    for symbol in list(held_days):
        if not any(p["symbol"] == symbol for p in positions):
            del held_days[symbol]
    state["bootstrap"] = False
    if reason:
        state["liquidating"] = reason
        state["entry_blocked"] = True
        state["entry_reason"] = reason
    if state.get("liquidating"):
        state["entry_blocked"] = True
        state["entry_reason"] = state["liquidating"]
    return daily


def entry_budget(config, account, positions, ask, atr_value):
    """Whole shares for bracket compatibility; capped by CASH, never margin."""
    equity = float(account["equity"])
    cash = max(0, float(account["cash"]))
    risk = config["risk"]
    allocated = equity * float(risk["capital_fraction"])
    deployed = sum(abs(float(p["market_value"])) for p in positions
                   if p["symbol"] in config["stock"]["symbols"])
    stop_distance = atr_value * risk["atr_stop_mult"]
    if stop_distance <= 0 or ask <= 0 or not isfinite(ask + stop_distance):
        return 0, 0.0
    limit = round(ask * 1.001 + .005, 2)
    budget = min(cash * .99, max(0, allocated-deployed),
                 allocated*risk["max_position_pct"],
                 allocated*risk["risk_per_trade"]/stop_distance*limit)
    return max(0, int(budget / limit)), limit
