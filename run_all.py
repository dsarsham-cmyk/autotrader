"""Run both trading scenarios (HIGH risk + LOW risk) as sibling processes.

Each scenario is a separate `bot.py` instance with its own config, state file,
logbook, and log file. They share one Alpaca paper account; `capital_fraction`
in each config limits how much of the account each bot may deploy so they do
not over-allocate.

The wrapper supervises both processes and restarts any that crash, so the pair
keeps running 24/7 on Railway.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

# (config path, human label) — order matters for log readability.
SCENARIOS = [
    ("config_high.yaml", "HIGH RISK"),
    ("config_low.yaml", "LOW RISK"),
]

RESTART_DELAY = 15  # seconds to wait before restarting a crashed scenario


def spawn(config: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "bot.py", config],
        cwd=str(Path(__file__).resolve().parent),
    )


def main() -> None:
    procs: list[tuple[str, str, subprocess.Popen]] = []
    for config, label in SCENARIOS:
        print(f"[run_all] starting {label} ({config})", flush=True)
        procs.append((config, label, spawn(config)))

    while True:
        for i, (config, label, p) in enumerate(procs):
            code = p.poll()
            if code is not None:
                print(f"[run_all] {label} ({config}) exited with code {code}; "
                      f"restarting in {RESTART_DELAY}s", flush=True)
                time.sleep(RESTART_DELAY)
                procs[i] = (config, label, spawn(config))
        time.sleep(5)


if __name__ == "__main__":
    main()
