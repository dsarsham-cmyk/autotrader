import run_all
import json
from datetime import datetime, timedelta, timezone
import pytest


class _Process:
    def __init__(self, code=None):
        self.code = code

    def poll(self):
        return self.code


def test_health_is_online_when_both_scenarios_run():
    procs = [
        ("config_high.yaml", "HIGH RISK", _Process()),
        ("config_low.yaml", "LOW RISK", _Process()),
    ]

    health = run_all.build_health(procs, {"HIGH RISK": 0, "LOW RISK": 1}, None)

    assert health["ok"] is True
    assert health["mode"] == "paper"
    assert health["scenarios"]["high"]["running"] is True
    assert health["scenarios"]["low"]["restarts"] == 1


def test_health_reports_a_stopped_scenario():
    procs = [
        ("config_high.yaml", "HIGH RISK", _Process(1)),
        ("config_low.yaml", "LOW RISK", _Process()),
    ]

    health = run_all.build_health(procs, {}, "2026-09-17")

    assert health["ok"] is False
    assert health["scenarios"]["high"]["running"] is False
    assert health["last_daily_report"] == "2026-09-17"


def test_live_dashboard_refresh_publishes_snapshot(monkeypatch, tmp_path):
    dashboard = tmp_path / "dashboard.json"
    payload = {"last_updated": "2026-09-18T00:00:00Z", "account": {"equity": 101000}}

    import snapshot
    monkeypatch.setattr(snapshot, "DASHBOARD", str(dashboard))
    monkeypatch.setattr(snapshot, "main", lambda: dashboard.write_text(
        json.dumps(payload), encoding="utf-8"
    ))
    run_all.LIVE_DASHBOARD_STATE.clear()

    result = run_all.refresh_live_dashboard_once()

    assert result == payload
    assert run_all.LIVE_DASHBOARD_STATE == payload


def test_both_portfolios_share_one_controller_health():
    health = run_all.build_health(
        [("safe_paper_engine.py", "PAPER ACCOUNT", _Process())],
        {"PAPER ACCOUNT": 2}, None)
    assert set(health["scenarios"]) == {"high", "low"}
    assert all(s["running"] and s["restarts"] == 2 for s in health["scenarios"].values())


def test_supervisor_cannot_spawn_legacy_writers():
    with pytest.raises(ValueError):
        run_all.spawn("config_high.yaml")


def test_safety_status_missing_or_stale_is_not_fresh(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert not run_all.read_safety_status()["fresh"]
    (tmp_path/"safety_status.json").write_text(json.dumps({
        "updated_at": (datetime.now(timezone.utc)-timedelta(seconds=60)).isoformat()}))
    assert not run_all.read_safety_status()["fresh"]
