"""Dashboard snapshot generator (read-only).

Reads the Alpaca paper account and splits it into the two live scenarios
(HIGH RISK / LOW RISK) so the GitHub Pages dashboard can show both. This runs
in GitHub Actions (read-only) and commits `dashboard.json`; it never places
orders.

The two scenarios share one Alpaca paper account and trade disjoint symbol
sets, so a position belongs to exactly one scenario based on its ticker.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml
from dotenv import load_dotenv

from price_feed import _retry_call

DASHBOARD = "dashboard.json"
STARTING_BALANCE = 100_000.0

# Scenario definitions mirror config_high.yaml / config_low.yaml.
SCENARIOS = [
    ("high", "config_high.yaml"),
    ("low", "config_low.yaml"),
]


def _recent_fills(api_key: str, api_secret: str, limit: int = 100) -> list[dict]:
    """Return the most recent completed order fills from Alpaca.

    Limited fallback sample only. Preserve individual execution quantities
    and prices; never multiply the final price by cumulative order quantity.
    The complete history below replaces this sample when available.
    """
    import urllib.request
    page_size = min(100, max(limit, 1))
    url = ("https://paper-api.alpaca.markets/v2/account/activities"
           f"?activity_types=FILL&direction=desc&page_size={page_size}")
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    })
    data = json.loads(urllib.request.urlopen(req, timeout=15).read())
    from account_history import compact_executions
    return compact_executions(data)[:limit]


def _enum_value(value) -> str:
    return str(getattr(value, "value", value or "")).lower()


def _order_inventory(client) -> tuple[list[dict], list[dict]]:
    """Return compact open/recent order metadata for protection auditing."""
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    def compact(order) -> dict:
        return {
            "id": str(order.id),
            "symbol": order.symbol or "",
            "side": _enum_value(order.side),
            "type": _enum_value(order.type),
            "order_class": _enum_value(order.order_class),
            "status": _enum_value(order.status),
            "created_at": order.created_at.isoformat() if order.created_at else "",
            "legs": [compact(leg) for leg in (order.legs or [])],
        }

    open_orders = _retry_call(
        client.get_orders,
        GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=100, nested=True),
    )
    recent_orders = _retry_call(
        client.get_orders,
        GetOrdersRequest(status=QueryOrderStatus.ALL, limit=100, nested=True),
    )
    return [compact(o) for o in open_orders], [compact(o) for o in recent_orders]


def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def build_audit(fills: list[dict], backtest: dict, positions: dict,
                open_orders: list[dict], recent_orders: list[dict],
                now: datetime) -> dict:
    """Build a plain-language, evidence-based engine health assessment."""
    eastern = ZoneInfo("America/New_York")
    now_et = now.astimezone(eastern)
    dated_fills = []
    for fill in fills:
        ts = _parse_time(fill.get("time", ""))
        if ts is not None:
            dated_fills.append((ts.astimezone(eastern), fill))

    by_day: dict[str, int] = {}
    for ts, _fill in dated_fills:
        key = ts.date().isoformat()
        by_day[key] = by_day.get(key, 0) + 1

    if dated_fills:
        first_day = min(ts.date() for ts, _ in dated_fills)
    else:
        first_day = now_et.date()
    observed_days = []
    cursor = first_day
    while cursor <= now_et.date():
        if cursor.weekday() < 5:
            observed_days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    active_days = sum(1 for day in observed_days if by_day.get(day, 0) > 0)
    active_rate = (active_days / len(observed_days) * 100) if observed_days else 0.0

    calendar = []
    cursor = now_et.date() - timedelta(days=13)
    while cursor <= now_et.date():
        if cursor.weekday() < 5:
            key = cursor.isoformat()
            calendar.append({"date": key, "fills": by_day.get(key, 0)})
        cursor += timedelta(days=1)

    # A sell followed by a buy in the same symbol within 30 minutes is churn,
    # not a new independent daily signal.
    churn_events = []
    chronological = sorted(dated_fills, key=lambda item: item[0])
    previous_by_symbol: dict[str, tuple[datetime, dict]] = {}
    for ts, fill in chronological:
        symbol = fill.get("symbol", "")
        prev = previous_by_symbol.get(symbol)
        if (prev and prev[1].get("side") == "sell" and fill.get("side") == "buy"
                and ts - prev[0] <= timedelta(minutes=30)):
            churn_events.append({
                "symbol": symbol,
                "minutes": round((ts - prev[0]).total_seconds() / 60, 1),
                "time": fill.get("time", ""),
            })
        previous_by_symbol[symbol] = (ts, fill)

    def flatten(orders: list[dict]) -> list[dict]:
        out = []
        for order in orders:
            out.append(order)
            out.extend(flatten(order.get("legs", [])))
        return out

    protective_types = {"stop", "stop_limit", "trailing_stop"}
    protected_symbols = {
        order.get("symbol", "")
        for order in flatten(open_orders)
        if order.get("type") in protective_types
    }
    open_symbols = set(positions)
    protected_count = len(open_symbols & protected_symbols)

    filled_buys = [
        order for order in recent_orders
        if order.get("side") == "buy" and order.get("status") == "filled"
    ]
    bracket_buys = sum(1 for order in filled_buys
                       if order.get("order_class") in {"bracket", "oto"})
    simple_buys = sum(1 for order in filled_buys
                      if order.get("order_class") == "simple")

    high = backtest.get("high", {})
    low = backtest.get("low", {})
    checks = []

    def check(key: str, label: str, status: str, detail: str) -> None:
        checks.append({"key": key, "label": label,
                       "status": status, "detail": detail})

    live_exits = sum(1 for _ts, fill in dated_fills if fill.get("side") == "sell")
    evidence_ok = len(observed_days) >= 30 and live_exits >= 30
    check(
        "live_evidence", "Enough live evidence", "good" if evidence_ok else "warn",
        (f"{len(observed_days)} observed trading days and {live_exits} sell fills. "
         + ("Enough for an initial live review."
            if evidence_ok else "Too early to judge live profitability reliably.")),
    )
    protection_ok = not open_symbols or protected_count == len(open_symbols)
    check(
        "risk_protection", "Broker-side protection",
        "good" if protection_ok else "bad",
        (f"{protected_count} of {len(open_symbols)} open positions have an active "
         "broker-side stop order. Recent filled buys: "
         f"{bracket_buys} bracket/OTO, {simple_buys} simple."),
    )
    check(
        "execution_churn", "No rapid exit/re-entry churn",
        "good" if not churn_events else "bad",
        ("No rapid churn detected." if not churn_events else
         f"Detected {len(churn_events)} sell-to-buy reversals within 30 minutes."),
    )
    high_ok = (high.get("profit_factor", 0) >= 1.3
               and high.get("sharpe", 0) >= 0.7
               and high.get("max_drawdown_pct", 100) <= 30)
    check(
        "high_backtest", "HIGH backtest quality", "good" if high_ok else "warn",
        f"Profit factor {high.get('profit_factor', 0):.2f}, Sharpe "
        f"{high.get('sharpe', 0):.2f}, max drawdown "
        f"{high.get('max_drawdown_pct', 0):.1f}%.",
    )
    low_ok = (low.get("profit_factor", 0) >= 1.3
              and low.get("sharpe", 0) >= 0.5
              and low.get("annualized_return_pct", 0) >= 2)
    check(
        "low_backtest", "LOW backtest quality", "good" if low_ok else "warn",
        f"Profit factor {low.get('profit_factor', 0):.2f}, Sharpe "
        f"{low.get('sharpe', 0):.2f}, annualized return "
        f"{low.get('annualized_return_pct', 0):.2f}%.",
    )

    bad_count = sum(c["status"] == "bad" for c in checks)
    verdict = "needs_attention" if bad_count else ("promising" if high_ok else "early")
    good_enough = bad_count == 0 and evidence_ok and high_ok

    return {
        "generated_at": now.isoformat(),
        "verdict": verdict,
        "good_enough": good_enough,
        "summary": (
            "Not ready to trust unattended: execution safeguards need attention."
            if bad_count else
            "Safeguards look healthy, but more live history is needed."
        ),
        "cadence": {
            "uses_daily_bars": True,
            "guaranteed_daily_trade": False,
            "fills_today": by_day.get(now_et.date().isoformat(), 0),
            "active_days": active_days,
            "observed_weekdays": len(observed_days),
            "active_day_pct": round(active_rate, 1),
            "calendar": calendar,
            "explanation": "The engine checks daily momentum. It may hold or make no trade; daily profit and daily fills are not guaranteed.",
        },
        "execution": {
            "recent_fill_count": len(dated_fills),
            "sell_fill_count": live_exits,
            "churn_count": len(churn_events),
            "churn_events": churn_events[-10:],
            "open_positions": len(open_symbols),
            "protected_positions": protected_count,
            "simple_buy_orders": simple_buys,
            "bracket_buy_orders": bracket_buys,
        },
        "checks": checks,
    }


def load_scenario_meta() -> dict:
    """Return {key: {name, symbols, capital_fraction, strategy}}."""
    out = {}
    for key, path in SCENARIOS:
        cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        out[key] = {
            "name": cfg.get("name", key.upper()),
            "symbols": cfg["stock"]["symbols"],
            "capital_fraction": cfg.get("risk", {}).get("capital_fraction", 0.5),
            "strategy": cfg["strategy"]["name"],
            "risk_per_trade": cfg.get("risk", {}).get("risk_per_trade", 0.01),
            "daily_loss_limit_pct": cfg.get("risk", {}).get("daily_loss_limit_pct", 0.03),
            "max_drawdown_pct": cfg.get("risk", {}).get("max_drawdown_pct", 0.20),
            "starting_equity": cfg.get("risk", {}).get("starting_equity", STARTING_BALANCE),
            "max_account_loss_pct": cfg.get("risk", {}).get("max_account_loss_pct", 0.10),
        }
    return out


def main() -> None:
    load_dotenv()
    api_key = os.getenv("ALPACA_API_KEY", "")
    api_secret = os.getenv("ALPACA_API_SECRET", "")

    meta = load_scenario_meta()
    symbol_to_scenario = {}
    for key, m in meta.items():
        for s in m["symbols"]:
            symbol_to_scenario[s] = key

    now = datetime.now(timezone.utc).isoformat()

    state = {
        "last_updated": now,
        "market_open": False,
        "account": {"equity": None, "cash": None, "buying_power": None,
                    "last_equity": None, "day_pnl": None, "day_pnl_pct": None,
                    "starting_balance": STARTING_BALANCE},
        "scenarios": {},
        "equity_history": [],
        "recent_trades": [],
        "backtest": {},
        "audit": {},
    }

    positions = {}
    positions_ok = False
    open_orders = []
    recent_orders = []

    if api_key and api_secret:
        from alpaca.trading.client import TradingClient
        client = TradingClient(api_key, api_secret, paper=True)
        try:
            acct = _retry_call(client.get_account)
            state["account"]["equity"] = float(acct.equity)
            state["account"]["cash"] = float(acct.cash)
            state["account"]["buying_power"] = float(acct.buying_power)
            last_equity = float(acct.last_equity)
            equity = float(acct.equity)
            state["account"]["last_equity"] = last_equity
            state["account"]["day_pnl"] = round(equity - last_equity, 2)
            state["account"]["day_pnl_pct"] = round(
                ((equity / last_equity) - 1) * 100 if last_equity else 0.0,
                3,
            )
        except Exception as e:
            print(f"[snapshot] account error: {e}", file=sys.stderr)
        try:
            state["market_open"] = bool(_retry_call(client.get_clock).is_open)
        except Exception:
            pass

        # Split positions by scenario.
        try:
            for p in _retry_call(client.get_all_positions):
                positions[p.symbol] = {
                    "qty": float(p.qty),
                    "entry_price": float(p.avg_entry_price),
                    "market_value": float(p.market_value or 0.0),
                    "unrealized_pnl": float(p.unrealized_pl or 0.0),
                    "unrealized_pnl_pct": float(p.unrealized_plpc or 0.0) * 100,
                    "current_price": float(p.current_price or p.avg_entry_price),
                    "previous_close": float(p.lastday_price) if p.lastday_price else None,
                }
            positions_ok = True
        except Exception as e:
            print(f"[snapshot] positions error: {e}", file=sys.stderr)

        for key, m in meta.items():
            sc_pos = {s: positions[s] for s in m["symbols"] if s in positions}
            mv = sum(p["market_value"] for p in sc_pos.values())
            upnl = sum(p["unrealized_pnl"] for p in sc_pos.values())
            state["scenarios"][key] = {
                "name": m["name"],
                "strategy": m["strategy"],
                "symbols": m["symbols"],
                "capital_fraction": m["capital_fraction"],
                "risk_per_trade": m["risk_per_trade"],
                "daily_loss_limit_pct": m["daily_loss_limit_pct"],
                "max_drawdown_pct": m["max_drawdown_pct"],
                "starting_equity": m["starting_equity"],
                "max_account_loss_pct": m["max_account_loss_pct"],
                "positions": sc_pos,
                "market_value": round(mv, 2),
                "unrealized_pnl": round(upnl, 2),
            }

        try:
            open_orders, recent_orders = _order_inventory(client)
        except Exception as e:
            print(f"[snapshot] order inventory error: {e}", file=sys.stderr)

    # Recent completed fills (authoritative, from Alpaca activities).
    if api_key and api_secret:
        try:
            state["recent_trades"] = _recent_fills(api_key, api_secret)
        except Exception as e:
            print(f"[snapshot] activities error: {e}", file=sys.stderr)

    state["positions_status"] = "available" if positions_ok else "unavailable"
    # Complete daily executions, including positions no longer held.
    # Never substitute since-entry P&L or zero when accounting is unavailable.
    state["daily_accounting"] = {"status": "unavailable"}
    if api_key and api_secret and positions_ok and state["account"]["equity"] is not None:
        try:
            from daily_pnl import build_daily
            daily = build_daily(meta, positions, api_key, api_secret,
                                state["account"]["day_pnl"], datetime.now(timezone.utc))
            state["daily_accounting"] = daily
            for key, values in daily["portfolios"].items():
                state["scenarios"][key].update(values)
        except Exception as e:
            state["daily_accounting"]["reason"] = str(e)
            print(f"[snapshot] daily accounting unavailable: {e}", file=sys.stderr)

    # A real dated history, not zeros inferred from a truncated recent list.
    state["account_history"] = {"status": "unavailable"}
    if api_key and api_secret:
        try:
            from account_history import history_base, build_history
            history_now = datetime.now(timezone.utc)
            current_fills = (state["daily_accounting"].get("executions")
                             if state["daily_accounting"]["status"] == "calculated" else None)
            history = build_history(history_base(api_key, api_secret, history_now),
                                    current_fills, state["account"], history_now,
                                    state["market_open"])
            state["account_history"] = history
            state["recent_trades"] = history["executions"]
        except Exception as e:
            state["account_history"]["reason"] = str(e)
            print(f"[snapshot] history unavailable: {e}", file=sys.stderr)

    # Expected performance from the committed backtest results.
    try:
        bt = json.loads(Path("backtest_results.json").read_text(encoding="utf-8"))
        state["backtest"] = {
            "high": bt.get("config_high.yaml", {}),
            "low": bt.get("config_low.yaml", {}),
        }
    except (OSError, json.JSONDecodeError):
        state["backtest"] = {}

    state["audit"] = build_audit(
        state["recent_trades"], state["backtest"], positions,
        open_orders, recent_orders, datetime.now(timezone.utc),
    )

    # Persist rolling equity history across snapshot runs.
    hist = []
    try:
        prev = json.loads(Path(DASHBOARD).read_text(encoding="utf-8"))
        hist = prev.get("equity_history", [])
    except (json.JSONDecodeError, OSError):
        pass
    eq = state["account"]["equity"]
    if eq is not None:
        pt = {"ts": now, "equity": eq}
        if not hist or hist[-1].get("ts") != pt["ts"]:
            hist.append(pt)
        hist = hist[-500:]
    state["equity_history"] = hist

    target = Path(DASHBOARD)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(target)
    print(f"[snapshot] wrote {DASHBOARD} | equity={eq} | "
          f"scenarios={list(state['scenarios'])}")


if __name__ == "__main__":
    main()
