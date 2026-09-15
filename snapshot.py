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
from datetime import datetime, timezone
from pathlib import Path

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
        "account": {"equity": None, "cash": None,
                    "starting_balance": STARTING_BALANCE},
        "scenarios": {},
        "equity_history": [],
    }

    if api_key and api_secret:
        from alpaca.trading.client import TradingClient
        client = TradingClient(api_key, api_secret, paper=True)
        try:
            acct = _retry_call(client.get_account)
            state["account"]["equity"] = float(acct.equity)
            state["account"]["cash"] = float(acct.cash)
        except Exception as e:
            print(f"[snapshot] account error: {e}", file=sys.stderr)
        try:
            state["market_open"] = bool(_retry_call(client.get_clock).is_open)
        except Exception:
            pass

        # Split positions by scenario.
        positions = {}
        try:
            for p in _retry_call(client.get_all_positions):
                positions[p.symbol] = {
                    "qty": float(p.qty),
                    "entry_price": float(p.avg_entry_price),
                    "market_value": float(p.market_value or 0.0),
                    "unrealized_pnl": float(p.unrealized_pl or 0.0),
                    "current_price": float(p.current_price or p.avg_entry_price),
                }
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
                "positions": sc_pos,
                "market_value": round(mv, 2),
                "unrealized_pnl": round(upnl, 2),
            }

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

    Path(DASHBOARD).write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"[snapshot] wrote {DASHBOARD} | equity={eq} | "
          f"scenarios={list(state['scenarios'])}")


if __name__ == "__main__":
    main()
