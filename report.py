"""Daily report generator — summarizes both scenarios + errors and sends it.

Reads the Alpaca paper account (split into HIGH RISK / LOW RISK), the two bot
log files, and the trade logbooks, then composes a plain-text report and sends
it via the configured alert channels (Telegram by default).

Usage
-----
    python report.py                 # build + send the report now
    python report.py --dry-run       # print the report without sending
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Windows consoles default to cp1252 and can't print emoji; force UTF-8 for
# local debugging. Telegram always receives UTF-8 regardless.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

STARTING_BALANCE = 100_000.0

# Scenario definitions mirror config_high.yaml / config_low.yaml.
SCENARIO_SYMBOLS = {
    "HIGH RISK": ["TQQQ", "SPXL", "SOXL"],
    "LOW RISK": ["QQQ", "SPY", "DIA", "IWM", "EWJ", "EZU", "EWU", "EWG"],
}
LOG_FILES = ["logs/trader_high.log", "logs/trader_low.log"]

ERROR_PATTERN = re.compile(r"(FAILED|loop error|Traceback|error|exception)",
                           re.IGNORECASE)


def _errors_today() -> list[str]:
    today = datetime.now(timezone.utc).date().isoformat()
    out = []
    for path in LOG_FILES:
        p = Path(path)
        if not p.exists():
            continue
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.startswith(today) and ERROR_PATTERN.search(line):
                    out.append(line.strip())
        except OSError:
            pass
    return out


def _account() -> dict:
    load_dotenv()
    api_key = os.getenv("ALPACA_API_KEY", "")
    api_secret = os.getenv("ALPACA_API_SECRET", "")
    if not (api_key and api_secret):
        return {}
    try:
        from alpaca.trading.client import TradingClient
        from price_feed import _retry_call
        client = TradingClient(api_key, api_secret, paper=True)
        acct = _retry_call(client.get_account)
        positions = {}
        for p in _retry_call(client.get_all_positions):
            positions[p.symbol] = {
                "market_value": float(p.market_value or 0.0),
                "unrealized_pnl": float(p.unrealized_pl or 0.0),
            }
        return {
            "equity": float(acct.equity),
            "cash": float(acct.cash),
            "positions": positions,
        }
    except Exception as e:
        print(f"[report] account error: {e}", file=sys.stderr)
        return {}


def build_report() -> str:
    acct = _account()
    equity = acct.get("equity")
    positions = acct.get("positions", {})
    errors = _errors_today()

    now = datetime.now(timezone.utc)
    lines = []
    lines.append("📊 Auto Trader — Daily Report")
    lines.append(f"📅 {now.date().isoformat()} ({now.strftime('%H:%M')} UTC)")
    lines.append("")

    if equity is not None:
        total_pnl = equity - STARTING_BALANCE
        total_pct = total_pnl / STARTING_BALANCE * 100.0
        lines.append(f"💰 Account equity: ${equity:,.2f}")
        lines.append(f"🏦 Total P&L: {total_pnl:+,.2f} ({total_pct:+.2f}%)")
    else:
        lines.append("💰 Account equity: n/a")
    lines.append("")

    # Per-scenario summary
    for name, syms in SCENARIO_SYMBOLS.items():
        sc_pos = {s: positions[s] for s in syms if s in positions}
        mv = sum(p["market_value"] for p in sc_pos.values())
        upnl = sum(p["unrealized_pnl"] for p in sc_pos.values())
        lines.append(f"🎯 {name} ({len(sc_pos)} positions, ${mv:,.2f}):")
        for s, p in sc_pos.items():
            lines.append(f"  • {s}: ${p['market_value']:,.2f} ({p['unrealized_pnl']:+,.2f})")
        lines.append(f"  → unrealized P&L: {upnl:+,.2f}")
        lines.append("")

    from run_all import read_safety_status
    safety = read_safety_status()
    errors.extend(safety.get("errors", []))
    lines.append("Paper safety: " + (safety.get("reason") or "checking"))
    lines.append(f"Verified stops: {safety.get('verified_stops', '?')}/{safety.get('open_positions', '?')}")
    if not safety.get("fresh"):
        errors.append("Safety controller status missing or stale")
    if safety.get("liquidating"):
        errors.append("Exit in progress; closure not yet confirmed")
    lines.append(f"⚠️ Errors / safety issues: {len(errors)}")
    if errors:
        for e in errors[:5]:
            lines.append(f"  • {e[:120]}")
    else:
        lines.append("No reported controller errors; see dashboard for current evidence")
    lines.append("")

    lines.append(f"Strategy: volatility_scaled_momentum (daily bars)")
    return "\n".join(lines)


def send_report() -> None:
    from alerts import AlertManager
    alerts = AlertManager()
    msg = build_report()
    alerts.send(msg)
    print(msg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily report")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the report without sending")
    args = parser.parse_args()
    if args.dry_run:
        print(build_report())
    else:
        send_report()


if __name__ == "__main__":
    main()
