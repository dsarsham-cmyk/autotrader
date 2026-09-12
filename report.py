"""Daily report generator — summarizes performance + errors and sends it.

Reads the live dashboard state, the runner log, and the trade logbook, then
composes a plain-text report and sends it via the configured alert channels
(Telegram by default).

Usage
-----
    python report.py                 # build + send the report now
    python report.py --dry-run       # print the report without sending
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows consoles default to cp1252 and can't print emoji; force UTF-8 for
# local debugging. Telegram always receives UTF-8 regardless.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DASHBOARD_STATE = "csmom_dashboard.json"
RUNNER_LOG = "logs/csmom_runner.log"
LOGBOOK = "logs/csmom_logbook.csv"
STARTING_BALANCE = 100_000.0

# Lines in the runner log that indicate a problem.
ERROR_PATTERN = re.compile(r"(FAILED|loop error|dashboard state error|Traceback|error)", re.IGNORECASE)


def _load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _errors_today() -> list[str]:
    """Return error lines from the runner log for today (UTC)."""
    p = Path(RUNNER_LOG)
    if not p.exists():
        return []
    today = _today_iso()
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith(today) and ERROR_PATTERN.search(line):
                out.append(line.strip())
    except OSError:
        pass
    return out


def _trades_today() -> list[dict]:
    """Return trades from the logbook for today (UTC)."""
    p = Path(LOGBOOK)
    if not p.exists():
        return []
    today = _today_iso()
    out = []
    try:
        with open(p, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = row.get("ts", "")
                action = row.get("action", "")
                # Skip dry-run placeholders; only count real orders.
                if ts.startswith(today) and "dry" not in action.lower():
                    out.append(row)
    except (OSError, csv.Error):
        pass
    return out


def _daily_pnl(state: dict) -> tuple[float, float]:
    """Return (daily_pnl, daily_pnl_pct) from the equity history."""
    hist = state.get("equity_history", [])
    if len(hist) < 2:
        return 0.0, 0.0
    today = _today_iso()
    todays = [h for h in hist if h.get("ts", "").startswith(today)]
    if len(todays) >= 2:
        first = todays[0]["equity"]
        last = todays[-1]["equity"]
    else:
        # Fall back to last two snapshots overall.
        first = hist[-2]["equity"]
        last = hist[-1]["equity"]
    pnl = last - first
    pct = (pnl / first * 100.0) if first else 0.0
    return pnl, pct


def build_report() -> str:
    state = _load_json(DASHBOARD_STATE)
    equity = state.get("equity")
    market_open = state.get("market_open", False)
    strategy = state.get("strategy", {})
    positions = state.get("positions", {})
    errors = _errors_today()
    trades = _trades_today()

    now = datetime.now(timezone.utc)
    lines = []
    lines.append("📊 Auto Trader — Daily Report")
    lines.append(f"📅 {now.date().isoformat()} ({now.strftime('%H:%M')} UTC)")
    lines.append("")

    # Equity / P&L
    if equity is not None:
        daily_pnl, daily_pct = _daily_pnl(state)
        total_pnl = equity - STARTING_BALANCE
        total_pct = total_pnl / STARTING_BALANCE * 100.0
        sign = "+" if daily_pnl >= 0 else ""
        lines.append(f"💰 Equity: ${equity:,.2f}")
        lines.append(f"📈 Today: {sign}{daily_pnl:,.2f} ({daily_pct:+.2f}%)")
        lines.append(f"🏦 Total P&L: {total_pnl:+,.2f} ({total_pct:+.2f}%)")
    else:
        lines.append("💰 Equity: n/a (no data yet)")
    lines.append("")

    # Open positions
    open_pos = {s: p for s, p in positions.items() if p.get("base_amount", 0) > 0}
    lines.append(f"📦 Open positions ({len(open_pos)}):")
    if open_pos:
        for s, p in open_pos.items():
            upnl = p.get("unrealized_pnl", 0.0)
            mv = p.get("market_value", 0.0)
            lines.append(f"  • {s}: ${mv:,.2f} ({upnl:+,.2f})")
    else:
        lines.append("  (none)")
    lines.append("")

    # Trades today
    lines.append(f"🔁 Trades today: {len(trades)}")
    for t in trades[:10]:
        lines.append(f"  • {t.get('action')} {t.get('symbol')} ${float(t.get('notional', 0) or 0):,.2f}")
    lines.append("")

    # Errors
    lines.append(f"⚠️ Errors today: {len(errors)}")
    if errors:
        for e in errors[:5]:
            lines.append(f"  • {e[:120]}")
    else:
        lines.append("✅ All systems normal")
    lines.append("")

    # Meta
    strat_name = strategy.get("name", "unknown")
    lines.append(f"Strategy: {strat_name} (top_k={strategy.get('top_k')}, "
                 f"rebalance={strategy.get('rebalance_days')}d)")
    lines.append(f"Market: {'open' if market_open else 'closed'}")

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
