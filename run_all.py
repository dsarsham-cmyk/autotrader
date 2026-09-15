"""Run both trading scenarios (HIGH risk + LOW risk) as sibling processes.

Each scenario is a separate `bot.py` instance with its own config, state file,
logbook, and log file. They share one Alpaca paper account; `capital_fraction`
in each config limits how much of the account each bot may deploy so they do
not over-allocate.

The wrapper supervises both processes, restarts any that crash, and sends the
daily Telegram report once per day (after US close, 21:00 UTC).
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# (config path, human label) — order matters for log readability.
SCENARIOS = [
    ("config_high.yaml", "HIGH RISK"),
    ("config_low.yaml", "LOW RISK"),
]

RESTART_DELAY = 15       # seconds to wait before restarting a crashed scenario
REPORT_HOUR = 21         # UTC hour to send the daily report (after US close)
REPORT_CHECK_SECONDS = 60


def spawn(config: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "bot.py", config],
        cwd=str(Path(__file__).resolve().parent),
    )


def maybe_send_daily_report(last_report_date: str | None) -> str | None:
    """Send the daily report once per day (after REPORT_HOUR UTC)."""
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    if last_report_date == today:
        return last_report_date
    if now.hour < REPORT_HOUR:
        return last_report_date
    try:
        from report import send_report
        send_report()
        print(f"[run_all] daily report sent ({today})", flush=True)
        return today
    except Exception as e:
        print(f"[run_all] report error: {e}", flush=True)
        return last_report_date


def main() -> None:
    procs: list[tuple[str, str, subprocess.Popen]] = []
    for config, label in SCENARIOS:
        print(f"[run_all] starting {label} ({config})", flush=True)
        procs.append((config, label, spawn(config)))

    last_report_date: str | None = None
    last_report_check = 0.0

    while True:
        for i, (config, label, p) in enumerate(procs):
            code = p.poll()
            if code is not None:
                print(f"[run_all] {label} ({config}) exited with code {code}; "
                      f"restarting in {RESTART_DELAY}s", flush=True)
                time.sleep(RESTART_DELAY)
                procs[i] = (config, label, spawn(config))

        now = time.time()
        if now - last_report_check >= REPORT_CHECK_SECONDS:
            last_report_check = now
            last_report_date = maybe_send_daily_report(last_report_date)

        time.sleep(5)


if __name__ == "__main__":
    main()
