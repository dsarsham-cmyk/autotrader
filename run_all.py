"""Supervise one paper-account execution controller for both portfolios."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# (config path, human label) — order matters for log readability.
SCENARIOS = [
    ("config_high.yaml", "HIGH RISK"),
    ("config_low.yaml", "LOW RISK"),
]

RESTART_DELAY = 15       # seconds to wait before restarting a crashed scenario
REPORT_HOUR = 21         # UTC hour to send the daily report (after US close)
REPORT_CHECK_SECONDS = 60
DASHBOARD_REFRESH_SECONDS = 10
SERVICE_STARTED_AT = datetime.now(timezone.utc).isoformat()
HEALTH_STATE: dict = {
    "ok": False,
    "service": "autotrader",
    "mode": "paper",
    "updated_at": SERVICE_STARTED_AT,
    "started_at": SERVICE_STARTED_AT,
    "scenarios": {},
}
HEALTH_LOCK = threading.Lock()
LIVE_DASHBOARD_STATE: dict = {}
LIVE_DASHBOARD_LOCK = threading.Lock()


def build_health(procs, restart_counts: dict[str, int],
                 last_report_date: str | None) -> dict:
    """Return a public, non-sensitive snapshot of the cloud engine."""
    scenarios = {}
    for _config, label, process in procs:
        labels = [name for _, name in SCENARIOS] if label == "PAPER ACCOUNT" else [label]
        for name in labels:
            scenarios[name.lower().replace(" risk", "")] = {
                "name": name, "running": process.poll() is None,
                "restarts": restart_counts.get(label, 0),
                "controller": "shared paper account",
            }
    return {
        "ok": bool(scenarios) and all(s["running"] for s in scenarios.values()),
        "service": "autotrader",
        "mode": "paper",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "started_at": SERVICE_STARTED_AT,
        "version": os.getenv("RAILWAY_GIT_COMMIT_SHA", "local")[:8],
        "last_daily_report": last_report_date,
        "scenarios": scenarios,
        "safety": read_safety_status(),
    }


def read_safety_status() -> dict:
    try:
        status = json.loads(Path("safety_status.json").read_text(encoding="utf-8"))
        age = (datetime.now(timezone.utc)-datetime.fromisoformat(status["updated_at"])).total_seconds()
        status["fresh"] = -5 <= age <= 45
        return status
    except (OSError, ValueError, KeyError, TypeError):
        return {"fresh": False, "errors": ["Safety controller status unavailable"]}


def publish_health(procs, restart_counts: dict[str, int],
                   last_report_date: str | None) -> None:
    with HEALTH_LOCK:
        HEALTH_STATE.clear()
        HEALTH_STATE.update(build_health(procs, restart_counts, last_report_date))


class HealthHandler(BaseHTTPRequestHandler):
    """Tiny read-only endpoint used by the web and Windows applications."""

    def _headers(self, status: int, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._headers(204)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", 1)[0]
        if path == "/dashboard.json":
            with LIVE_DASHBOARD_LOCK:
                payload = dict(LIVE_DASHBOARD_STATE)
            self._headers(200 if payload else 503)
            self.wfile.write(json.dumps(
                payload or {"error": "live dashboard is starting"}
            ).encode("utf-8"))
            return
        if path not in ("/", "/health", "/status.json"):
            self._headers(404)
            self.wfile.write(b'{"error":"not found"}')
            return
        with HEALTH_LOCK:
            payload = dict(HEALTH_STATE)
        self._headers(200 if payload.get("ok") else 503)
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def log_message(self, _format: str, *_args) -> None:
        return


def start_health_server() -> ThreadingHTTPServer | None:
    port = int(os.getenv("PORT", "0") or 0)
    if not port:
        return None
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[run_all] health endpoint listening on :{port}", flush=True)
    return server


def refresh_live_dashboard_once() -> dict:
    """Build a read-only Alpaca snapshot for the live web dashboard."""
    import snapshot

    snapshot.main()
    payload = json.loads(Path(snapshot.DASHBOARD).read_text(encoding="utf-8"))
    with LIVE_DASHBOARD_LOCK:
        LIVE_DASHBOARD_STATE.clear()
        LIVE_DASHBOARD_STATE.update(payload)
    return payload


def dashboard_refresh_loop() -> None:
    while True:
        started = time.time()
        try:
            refresh_live_dashboard_once()
        except Exception as e:
            print(f"[run_all] live dashboard refresh error: {e}", flush=True)
        elapsed = time.time() - started
        time.sleep(max(1, DASHBOARD_REFRESH_SECONDS - elapsed))


def start_dashboard_refresher() -> None:
    threading.Thread(target=dashboard_refresh_loop, daemon=True).start()
    print("[run_all] live dashboard refresh every 10 seconds", flush=True)


def spawn(config: str) -> subprocess.Popen:
    if config != "safe_paper_engine.py":
        raise ValueError("Production supervisor requires the single paper safety engine")
    return subprocess.Popen(
        [sys.executable, config],
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
    for config, label in [("safe_paper_engine.py", "PAPER ACCOUNT")]:
        print(f"[run_all] starting {label} ({config})", flush=True)
        procs.append((config, label, spawn(config)))

    last_report_date: str | None = None
    last_report_check = 0.0
    restart_counts = {"PAPER ACCOUNT": 0}
    publish_health(procs, restart_counts, last_report_date)
    start_health_server()
    start_dashboard_refresher()

    while True:
        for i, (config, label, p) in enumerate(procs):
            code = p.poll()
            if code is not None:
                print(f"[run_all] {label} ({config}) exited with code {code}; "
                      f"restarting in {RESTART_DELAY}s", flush=True)
                time.sleep(RESTART_DELAY)
                procs[i] = (config, label, spawn(config))
                restart_counts[label] += 1

        now = time.time()
        if now - last_report_check >= REPORT_CHECK_SECONDS:
            last_report_check = now
            last_report_date = maybe_send_daily_report(last_report_date)

        publish_health(procs, restart_counts, last_report_date)
        time.sleep(5)


if __name__ == "__main__":
    main()
